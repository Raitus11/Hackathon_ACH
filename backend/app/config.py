"""Config/rule service: loads the external YAML rule set safely and validates it.

The file is re-read on every validation run, so editing the YAML and re-running is the whole
"rule change" procedure. No application code is touched (AC4).
"""

from __future__ import annotations

import hashlib
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from .models import StrictModel

MAX_CONFIG_BYTES = 256 * 1024

Normalizer = Literal["trim", "casefold", "upper", "digits_only", "decimal", "sorted_csv"]

# Placeholders a reason template may use. Anything else is rejected at load time, which also
# blocks attribute/index access tricks such as "{field.__class__}".
TEMPLATE_PLACEHOLDERS = frozenset(
    {
        "rule_id",
        "field",
        "field_label",
        "expected",
        "actual",
        "request_id",
        "request_type",
        "status",
        "indicator",
        "indicator_label",
        "changed_count",
        "changed_by",
        "record_id",
    }
)


class ConfigError(Exception):
    def __init__(self, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class FieldDef(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    normalize: list[Normalizer] = Field(default_factory=lambda: ["trim"])


def _check_template(value: str) -> str:
    for _, name, spec, conv in string.Formatter().parse(value):
        if name is None:
            continue
        if name not in TEMPLATE_PLACEHOLDERS:
            raise ValueError(
                f"unknown placeholder '{{{name}}}'; allowed: {', '.join(sorted(TEMPLATE_PLACEHOLDERS))}"
            )
        if spec or conv:
            raise ValueError(f"format specs and conversions are not allowed in '{{{name}}}'")
    return value


class RuleBase(StrictModel):
    id: str = Field(pattern=r"^[A-Z]{2,5}-\d{3}$")
    version: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=200)
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    enabled: bool = True
    reason_template: str = Field(min_length=1, max_length=400)
    match_template: str = Field(default="Value matches the configured expectation.", max_length=400)

    @field_validator("reason_template", "match_template")
    @classmethod
    def _templates(cls, value: str) -> str:
        return _check_template(value)


FieldScope = Union[Literal["requested_fields"], list[str]]


class RequestApprovedRule(RuleBase):
    type: Literal["request_approved"]
    approved_statuses: list[str] = Field(min_length=1)


class RequiredRule(RuleBase):
    type: Literal["required"]
    applies_to: FieldScope = "requested_fields"


class EqualityRule(RuleBase):
    type: Literal["equality"]
    applies_to: FieldScope = "requested_fields"


class AuthorizedScopeRule(RuleBase):
    type: Literal["authorized_scope"]
    exempt_fields: list[str] = Field(default_factory=list)


class SourceConsistencyRule(RuleBase):
    type: Literal["source_consistency"]
    compare: Literal["tnal_vs_gps"] = "tnal_vs_gps"


class RequiredWhen(StrictModel):
    always: bool = False
    request_types: list[str] = Field(default_factory=list)
    fields_changed_any: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_empty(self) -> "RequiredWhen":
        if not (self.always or self.request_types or self.fields_changed_any):
            raise ValueError("required_when needs always: true, request_types or fields_changed_any")
        return self


class EvidencePresentRule(RuleBase):
    type: Literal["evidence_present"]
    indicator: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    indicator_label: str = Field(min_length=1, max_length=80)
    required_when: RequiredWhen


Rule = Annotated[
    Union[
        RequestApprovedRule,
        RequiredRule,
        EqualityRule,
        AuthorizedScopeRule,
        SourceConsistencyRule,
        EvidencePresentRule,
    ],
    Field(discriminator="type"),
]


class RuleSetMeta(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    control_id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    effective_date: str
    owner: str
    description: str
    data_classification: Literal["SYNTHETIC"] = "SYNTHETIC"


class RuleSet(StrictModel):
    ruleset: RuleSetMeta
    fields: dict[str, FieldDef] = Field(min_length=1)
    rules: list[Rule] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistency(self) -> "RuleSet":
        ids = [rule.id for rule in self.rules]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        if duplicates:
            raise ValueError(f"duplicate rule ids: {', '.join(duplicates)}")
        for rule in self.rules:
            scope = getattr(rule, "applies_to", None)
            if isinstance(scope, list):
                unknown = [f for f in scope if f not in self.fields]
                if unknown:
                    raise ValueError(f"{rule.id} applies_to unknown fields: {', '.join(unknown)}")
        return self

    def label(self, field: str) -> str:
        definition = self.fields.get(field)
        return definition.label if definition else field

    def normalizers(self, field: str) -> list[str]:
        definition = self.fields.get(field)
        return list(definition.normalize) if definition else ["trim"]


@dataclass(frozen=True)
class LoadedConfig:
    ruleset: RuleSet
    raw_text: str
    sha256: str
    path: Path
    loaded_at: datetime

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]


def load_ruleset(path: Path) -> LoadedConfig:
    if not path.is_file():
        raise ConfigError(f"Rule configuration not found: {path.name}")
    raw = path.read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
        raise ConfigError(f"Rule configuration exceeds {MAX_CONFIG_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("Rule configuration must be UTF-8 text") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        detail = {"line": mark.line + 1, "column": mark.column + 1} if mark else {}
        raise ConfigError(f"Rule configuration is not valid YAML: {getattr(exc, 'problem', exc)}", [detail]) from exc
    if not isinstance(data, dict):
        raise ConfigError("Rule configuration must be a YAML mapping")
    try:
        ruleset = RuleSet.model_validate(data)
    except ValidationError as exc:
        details = [
            {"location": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors(include_url=False, include_input=False)
        ]
        raise ConfigError("Rule configuration failed schema validation", details) from exc
    return LoadedConfig(
        ruleset=ruleset,
        raw_text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
        path=path,
        loaded_at=datetime.now(timezone.utc),
    )
