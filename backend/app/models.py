"""Typed models: synthetic inputs, canonical case, immutable findings, separate human decision.

The engine result (ValidationResult) deliberately has no approval field. The only place an
Approve or Investigate decision exists is DecisionRecord, which only a checker can create.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SYNTHETIC = "SYNTHETIC"
DECISION_SUPPORT_NOTICE = (
    "Decision support only. This result is not an approval. "
    "The independent checker records the final Approve or Investigate decision."
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- inputs (synthetic)


class RequestedChange(StrictModel):
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    requested_value: str = Field(max_length=256)


class MaintenanceRequest(StrictModel):
    """Synthetic customer maintenance request (simulates ServiceNow / Fulfillment Platform)."""

    request_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(min_length=1, max_length=128)
    request_type: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=32)
    submitted_by: str = Field(min_length=1, max_length=64)
    approved_by: str | None = Field(default=None, max_length=64)
    approved_at: datetime | None = None
    requested_changes: list[RequestedChange] = Field(min_length=1, max_length=50)
    evidence: dict[str, bool] = Field(default_factory=dict)
    source_system: str = "ServiceNow / Fulfillment Platform (SIMULATED)"
    data_classification: Literal["SYNTHETIC"] = SYNTHETIC

    @field_validator("requested_changes")
    @classmethod
    def _unique_fields(cls, value: list[RequestedChange]) -> list[RequestedChange]:
        seen: set[str] = set()
        for change in value:
            if change.field in seen:
                raise ValueError(f"field '{change.field}' is requested more than once")
            seen.add(change.field)
        return value


class TnalEntry(StrictModel):
    """One row of the simulated TNAL Critical Field Audit Log."""

    record_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    old_value: str | None = Field(default=None, max_length=256)
    new_value: str | None = Field(default=None, max_length=256)
    changed_by: str = Field(min_length=1, max_length=64)
    changed_at: datetime


class GpsChange(StrictModel):
    """One line of the simulated GPS Customer Data Change Report."""

    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    new_value: str | None = Field(default=None, max_length=256)


class ImplementedChange(StrictModel):
    """Synthetic implemented-change record (simulated TNAL + GPS reports)."""

    change_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    implemented_by: str = Field(min_length=1, max_length=64)
    implemented_at: datetime
    tnal_entries: list[TnalEntry] = Field(max_length=200)
    gps_changes: list[GpsChange] = Field(default_factory=list, max_length=200)
    source_systems: list[str] = Field(
        default_factory=lambda: [
            "TNAL Critical Field Audit Log (SIMULATED)",
            "GPS Customer Data Change Report (SIMULATED)",
        ]
    )
    data_classification: Literal["SYNTHETIC"] = SYNTHETIC


# ---------------------------------------------------------------- canonical model


class ImplementedValue(FrozenModel):
    field: str
    old_value: str | None
    new_value: str | None
    record_id: str
    changed_by: str
    changed_at: datetime


class MaintenanceCase(FrozenModel):
    """Canonical ACH maintenance model produced by ingest + match + normalize."""

    request: MaintenanceRequest
    change: ImplementedChange
    requested: dict[str, str]
    implemented: dict[str, ImplementedValue]
    gps: dict[str, str | None]
    evidence: dict[str, bool]
    input_digest: str


# ---------------------------------------------------------------- results


class Outcome(str, Enum):
    PASS = "PASS"
    EXCEPTION = "EXCEPTION"


class FindingResult(str, Enum):
    MATCH = "MATCH"
    EXCEPTION = "EXCEPTION"


class ExceptionType(str, Enum):
    REQUEST_NOT_APPROVED = "REQUEST_NOT_APPROVED"
    MISSING_FIELD = "MISSING_FIELD"
    MISMATCH = "MISMATCH"
    UNAUTHORIZED_CHANGE = "UNAUTHORIZED_CHANGE"
    SOURCE_INCONSISTENT = "SOURCE_INCONSISTENT"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


class Finding(FrozenModel):
    finding_id: str
    rule_id: str
    rule_version: int
    rule_type: str
    rule_description: str
    severity: str
    field: str
    field_label: str
    expected_value: str | None
    expected_source: str
    actual_value: str | None
    actual_source: str
    result: FindingResult
    exception_type: ExceptionType | None
    reason: str

    @model_validator(mode="after")
    def _exception_has_type(self) -> "Finding":
        if (self.result is FindingResult.EXCEPTION) != (self.exception_type is not None):
            raise ValueError("exception findings must carry an exception_type and matches must not")
        return self


class RuleEvaluation(FrozenModel):
    rule_id: str
    rule_version: int
    rule_type: str
    description: str
    status: Literal["EVALUATED", "NOT_APPLICABLE", "DISABLED"]
    checks: int
    exceptions: int


class ValidationResult(FrozenModel):
    run_id: str
    evaluated_at: datetime
    scenario_id: str | None
    request_id: str
    change_id: str
    customer_id: str
    customer_name: str
    implemented_by: str
    overall: Outcome
    exception_count: int
    match_count: int
    findings: tuple[Finding, ...]
    rule_evaluations: tuple[RuleEvaluation, ...]
    summary_reasons: tuple[str, ...]
    ruleset_id: str
    control_id: str
    config_version: str
    config_hash: str
    config_file: str
    input_digest: str
    findings_digest: str
    decision_support_notice: str = DECISION_SUPPORT_NOTICE
    data_classification: Literal["SYNTHETIC"] = SYNTHETIC


# ---------------------------------------------------------------- human decision


class DecisionType(str, Enum):
    APPROVE = "APPROVE"
    INVESTIGATE = "INVESTIGATE"


class DecisionInput(StrictModel):
    decision: DecisionType
    comment: str = Field(min_length=5, max_length=2000)
    acknowledge_exceptions: bool = False
    ai_review_confirmed: bool = False


class DecisionRecord(FrozenModel):
    decision_id: str
    run_id: str
    decision: DecisionType
    actor_id: str
    actor_name: str
    actor_role: str
    comment: str
    acknowledged_exceptions: bool
    ai_review_confirmed: bool = False
    engine_outcome: Outcome
    config_hash: str
    recorded_at: datetime


class Persona(FrozenModel):
    id: str
    name: str
    role: Literal["MAKER", "CHECKER"]
    title: str


# ---------------------------------------------------------------- AI-assisted extraction (advisory)


class Agreement(str, Enum):
    AGREES = "AGREES"
    DISAGREES = "DISAGREES"
    NOT_IN_DOCUMENT = "NOT_IN_DOCUMENT"
    NOT_IN_REQUEST = "NOT_IN_REQUEST"


class ExtractedField(FrozenModel):
    name: str
    label: str
    extracted_value: str | None
    confidence: float = Field(ge=0, le=1)
    request_value: str | None
    agreement: Agreement


class DocumentExtraction(FrozenModel):
    """Output of the Document Extraction Agent. Advisory only: it is shown to the checker,
    must be confirmed, and is never an input to the PASS/EXCEPTION decision."""

    status: Literal["EXTRACTED", "NO_DOCUMENT", "FAILED"]
    ai_assisted: bool = True
    document_id: str | None = None
    document_type: str = "CUSTOMER_AUTHORIZATION_FORM"
    provider: str
    model: str
    simulated: bool
    prompt_version: str
    cache: Literal["MISS", "HIT_LOCAL", "NONE"] = "NONE"
    fields: tuple[ExtractedField, ...] = ()
    signature_present: bool | None = None
    signature_confidence: float | None = None
    date_signed: str | None = None
    disagreements: int = 0
    low_confidence: int = 0
    notes: str | None = None
    error: str | None = None
    notice: str = (
        "AI-ASSISTED extraction. Advisory only: values must be reviewed by the checker and do not "
        "change the PASS/EXCEPTION result, which is decided by the configured deterministic rules."
    )


class AgentStep(FrozenModel):
    order: int
    agent: str
    responsibility: str
    kind: Literal["DETERMINISTIC", "AI_ASSISTED"]
    status: Literal["OK", "EXCEPTIONS_FOUND", "NO_DOCUMENT", "FAILED", "SKIPPED"]
    duration_ms: float
    summary: str
    output: dict
