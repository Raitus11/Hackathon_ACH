"""Validation engine: deterministic, config-driven, returns immutable findings.

Same inputs + same config file => same findings and the same findings_digest (idempotent).
The engine output carries no approval status; PASS and EXCEPTION are decision support only.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from .config import LoadedConfig, RequiredRule
from .models import (
    Finding,
    FindingResult,
    MaintenanceCase,
    Outcome,
    RuleEvaluation,
    ValidationResult,
)
from .rules.evaluators import EVALUATORS, Context


def _required_fields(case: MaintenanceCase, cfg: LoadedConfig) -> frozenset[str]:
    covered: set[str] = set()
    for rule in cfg.ruleset.rules:
        if isinstance(rule, RequiredRule) and rule.enabled:
            covered |= set(case.requested) if rule.applies_to == "requested_fields" else set(rule.applies_to)
    return frozenset(covered)


def _label(rule: object, field: str, ruleset: object) -> str:
    if field == "*":
        return "GPS report vs TNAL" if getattr(rule, "type", "") == "source_consistency" else "All changed fields"
    if field == "request.status":
        return "Request status"
    if field.startswith("evidence."):
        return getattr(rule, "indicator_label", field)
    return ruleset.label(field)  # type: ignore[attr-defined]


def evaluate(
    case: MaintenanceCase,
    cfg: LoadedConfig,
    *,
    scenario_id: str | None = None,
    run_id: str | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    ruleset = cfg.ruleset
    ctx = Context(case=case, ruleset=ruleset, required_fields=_required_fields(case, cfg))

    findings: list[Finding] = []
    evaluations: list[RuleEvaluation] = []
    for rule in ruleset.rules:
        if not rule.enabled:
            evaluations.append(
                RuleEvaluation(rule_id=rule.id, rule_version=rule.version, rule_type=rule.type,
                               description=rule.description, status="DISABLED", checks=0, exceptions=0)
            )
            continue
        output = EVALUATORS[rule.type](rule, ctx)
        exceptions = 0
        for draft in output.drafts:
            exceptions += draft.result is FindingResult.EXCEPTION
            label = _label(rule, draft.field, ruleset)
            findings.append(
                Finding(
                    finding_id=f"F-{len(findings) + 1:02d}",
                    rule_id=rule.id,
                    rule_version=rule.version,
                    rule_type=rule.type,
                    rule_description=rule.description,
                    severity=rule.severity,
                    field=draft.field,
                    field_label=label,
                    expected_value=draft.expected_value,
                    expected_source=draft.expected_source,
                    actual_value=draft.actual_value,
                    actual_source=draft.actual_source,
                    result=draft.result,
                    exception_type=draft.exception_type,
                    reason=draft.reason,
                )
            )
        evaluations.append(
            RuleEvaluation(rule_id=rule.id, rule_version=rule.version, rule_type=rule.type,
                           description=rule.description, status=output.status,  # type: ignore[arg-type]
                           checks=output.checks, exceptions=exceptions)
        )

    exception_findings = [f for f in findings if f.result is FindingResult.EXCEPTION]
    overall = Outcome.EXCEPTION if exception_findings else Outcome.PASS
    if exception_findings:
        reasons = tuple(f"{f.rule_id} v{f.rule_version}: {f.reason}" for f in exception_findings)
    else:
        evaluated = sum(1 for e in evaluations if e.status == "EVALUATED")
        reasons = (
            f"All {evaluated} applicable configured rules passed "
            f"({sum(e.checks for e in evaluations)} checks). Checker review and decision are still required.",
        )

    digest_payload = json.dumps(
        {
            "config_hash": cfg.sha256,
            "input_digest": case.input_digest,
            "overall": overall.value,
            "findings": [f.model_dump(mode="json") for f in findings],
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    return ValidationResult(
        run_id=run_id or f"RUN-{uuid.uuid4().hex[:12].upper()}",
        evaluated_at=now or datetime.now(timezone.utc),
        scenario_id=scenario_id,
        request_id=case.request.request_id,
        change_id=case.change.change_id,
        customer_id=case.request.customer_id,
        customer_name=case.request.customer_name,
        implemented_by=case.change.implemented_by,
        overall=overall,
        exception_count=len(exception_findings),
        match_count=len(findings) - len(exception_findings),
        findings=tuple(findings),
        rule_evaluations=tuple(evaluations),
        summary_reasons=reasons,
        ruleset_id=ruleset.ruleset.id,
        control_id=ruleset.ruleset.control_id,
        config_version=ruleset.ruleset.version,
        config_hash=cfg.sha256,
        config_file=cfg.path.name,
        input_digest=case.input_digest,
        findings_digest=hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
    )
