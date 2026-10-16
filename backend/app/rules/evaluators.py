"""One deterministic evaluator per configured rule type.

Evaluators never decide approval. They only report MATCH or EXCEPTION per check, with the
expected value, the actual value, where each came from, and a reason rendered from config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import (
    AuthorizedScopeRule,
    EqualityRule,
    EvidencePresentRule,
    RequestApprovedRule,
    RequiredRule,
    RuleSet,
    SourceConsistencyRule,
)
from ..explain import show, render
from ..models import ExceptionType, FindingResult, MaintenanceCase
from ..normalize import is_blank, normalize


@dataclass(frozen=True)
class Draft:
    field: str
    expected_value: str | None
    expected_source: str
    actual_value: str | None
    actual_source: str
    result: FindingResult
    exception_type: ExceptionType | None
    reason: str


@dataclass
class EvalOutput:
    status: str = "EVALUATED"  # EVALUATED | NOT_APPLICABLE
    checks: int = 0
    drafts: list[Draft] = field(default_factory=list)


@dataclass(frozen=True)
class Context:
    case: MaintenanceCase
    ruleset: RuleSet
    required_fields: frozenset[str]  # fields covered by an enabled `required` rule

    # source labels (every system is simulated)
    @property
    def request_src(self) -> str:
        return f"ServiceNow request {self.case.request.request_id} (SIMULATED)"

    @property
    def gps_src(self) -> str:
        return f"GPS change report {self.case.change.change_id} (SIMULATED)"

    @property
    def dms_src(self) -> str:
        return f"DMS evidence indicators on {self.case.request.request_id} (SIMULATED)"

    def tnal_src(self, fld: str) -> str:
        imp = self.case.implemented.get(fld)
        rec = imp.record_id if imp else "no row"
        return f"TNAL {rec} (SIMULATED)"

    def norm(self, fld: str, value: str | None) -> str | None:
        return normalize(value, self.ruleset.normalizers(fld))

    def scope(self, applies_to: object) -> list[str]:
        if applies_to == "requested_fields":
            return list(self.case.requested.keys())
        return list(applies_to)  # type: ignore[arg-type]

    def base_values(self, rule_id: str) -> dict[str, object]:
        r = self.case.request
        return {"rule_id": rule_id, "request_id": r.request_id, "request_type": r.request_type, "status": r.status}


def _request_approved(rule: RequestApprovedRule, ctx: Context) -> EvalOutput:
    status = ctx.case.request.status
    ok = status.strip().upper() in {s.upper() for s in rule.approved_statuses}
    expected = " or ".join(rule.approved_statuses)
    values = ctx.base_values(rule.id) | {"field": "status", "field_label": "Request status",
                                         "expected": expected, "actual": show(status)}
    return EvalOutput(
        checks=1,
        drafts=[
            Draft(
                field="request.status",
                expected_value=expected,
                expected_source=f"Rule config {rule.id} v{rule.version}",
                actual_value=status,
                actual_source=ctx.request_src,
                result=FindingResult.MATCH if ok else FindingResult.EXCEPTION,
                exception_type=None if ok else ExceptionType.REQUEST_NOT_APPROVED,
                reason=render(rule.match_template if ok else rule.reason_template, **values),
            )
        ],
    )


def _required(rule: RequiredRule, ctx: Context) -> EvalOutput:
    out = EvalOutput()
    for fld in ctx.scope(rule.applies_to):
        out.checks += 1
        imp = ctx.case.implemented.get(fld)
        actual = imp.new_value if imp else None
        if not is_blank(actual):
            continue  # presence is confirmed; the equality rule reports the value comparison
        expected = ctx.case.requested.get(fld)
        values = ctx.base_values(rule.id) | {
            "field": fld, "field_label": ctx.ruleset.label(fld),
            "expected": show(expected) if expected is not None else "a non-blank value",
            "actual": show(actual), "record_id": imp.record_id if imp else "none",
        }
        out.drafts.append(
            Draft(
                field=fld,
                expected_value=expected,
                expected_source=ctx.request_src if expected is not None else f"Rule config {rule.id} v{rule.version}",
                actual_value=actual,
                actual_source=ctx.tnal_src(fld),
                result=FindingResult.EXCEPTION,
                exception_type=ExceptionType.MISSING_FIELD,
                reason=render(rule.reason_template, **values),
            )
        )
    return out


def _equality(rule: EqualityRule, ctx: Context) -> EvalOutput:
    out = EvalOutput()
    for fld in ctx.scope(rule.applies_to):
        expected = ctx.case.requested.get(fld)
        if expected is None:
            continue  # nothing was requested for this field, so there is no expected value
        imp = ctx.case.implemented.get(fld)
        actual = imp.new_value if imp else None
        if is_blank(actual) and fld in ctx.required_fields:
            continue  # reported once, as MISSING_FIELD, by the required rule (precedence)
        out.checks += 1
        ok = not is_blank(actual) and ctx.norm(fld, expected) == ctx.norm(fld, actual)
        values = ctx.base_values(rule.id) | {
            "field": fld, "field_label": ctx.ruleset.label(fld), "expected": show(expected),
            "actual": show(actual), "record_id": imp.record_id if imp else "none",
            "changed_by": imp.changed_by if imp else "",
        }
        out.drafts.append(
            Draft(
                field=fld,
                expected_value=expected,
                expected_source=ctx.request_src,
                actual_value=actual,
                actual_source=ctx.tnal_src(fld),
                result=FindingResult.MATCH if ok else FindingResult.EXCEPTION,
                exception_type=None if ok else ExceptionType.MISMATCH,
                reason=render(rule.match_template if ok else rule.reason_template, **values),
            )
        )
    return out


def _authorized_scope(rule: AuthorizedScopeRule, ctx: Context) -> EvalOutput:
    out = EvalOutput()
    changed = [
        imp for fld, imp in ctx.case.implemented.items()
        if ctx.norm(fld, imp.old_value) != ctx.norm(fld, imp.new_value)
    ]
    out.checks = len(changed)
    unauthorized = [
        imp for imp in changed
        if imp.field not in ctx.case.requested and imp.field not in rule.exempt_fields
    ]
    for imp in unauthorized:
        values = ctx.base_values(rule.id) | {
            "field": imp.field, "field_label": ctx.ruleset.label(imp.field),
            "expected": show(imp.old_value), "actual": show(imp.new_value),
            "record_id": imp.record_id, "changed_by": imp.changed_by,
        }
        out.drafts.append(
            Draft(
                field=imp.field,
                expected_value=imp.old_value,
                expected_source=f"{ctx.request_src}: field not in requested changes, so no change expected",
                actual_value=imp.new_value,
                actual_source=ctx.tnal_src(imp.field),
                result=FindingResult.EXCEPTION,
                exception_type=ExceptionType.UNAUTHORIZED_CHANGE,
                reason=render(rule.reason_template, **values),
            )
        )
    if not unauthorized:
        values = ctx.base_values(rule.id) | {"changed_count": len(changed), "field": "*", "field_label": "All changed fields"}
        out.drafts.append(
            Draft(
                field="*",
                expected_value="Only requested fields changed",
                expected_source=ctx.request_src,
                actual_value=f"{len(changed)} changed field(s), all requested",
                actual_source=f"TNAL change log for {ctx.case.change.change_id} (SIMULATED)",
                result=FindingResult.MATCH,
                exception_type=None,
                reason=render(rule.match_template, **values),
            )
        )
    return out


def _source_consistency(rule: SourceConsistencyRule, ctx: Context) -> EvalOutput:
    out = EvalOutput()
    fields = sorted(set(ctx.case.implemented) | set(ctx.case.gps))
    problems: list[Draft] = []
    for fld in fields:
        out.checks += 1
        imp = ctx.case.implemented.get(fld)
        tnal_value = imp.new_value if imp else None
        in_gps = fld in ctx.case.gps
        gps_value = ctx.case.gps.get(fld)
        consistent = imp is not None and in_gps and ctx.norm(fld, tnal_value or "") == ctx.norm(fld, gps_value or "")
        if consistent:
            continue
        values = ctx.base_values(rule.id) | {
            "field": fld, "field_label": ctx.ruleset.label(fld),
            "expected": show(tnal_value) if imp else "<no TNAL row>",
            "actual": show(gps_value) if in_gps else "<not on GPS report>",
        }
        problems.append(
            Draft(
                field=fld,
                expected_value=tnal_value,
                expected_source=ctx.tnal_src(fld),
                actual_value=gps_value,
                actual_source=ctx.gps_src,
                result=FindingResult.EXCEPTION,
                exception_type=ExceptionType.SOURCE_INCONSISTENT,
                reason=render(rule.reason_template, **values),
            )
        )
    out.drafts = problems or [
        Draft(
            field="*",
            expected_value=f"{len(fields)} field(s) per TNAL",
            expected_source=f"TNAL change log for {ctx.case.change.change_id} (SIMULATED)",
            actual_value=f"{len(fields)} field(s) per GPS, values agree",
            actual_source=ctx.gps_src,
            result=FindingResult.MATCH,
            exception_type=None,
            reason=render(rule.match_template, **(ctx.base_values(rule.id) | {"changed_count": len(fields)})),
        )
    ]
    return out


def _evidence_present(rule: EvidencePresentRule, ctx: Context) -> EvalOutput:
    when = rule.required_when
    touched = set(ctx.case.requested) | {
        f for f, imp in ctx.case.implemented.items() if ctx.norm(f, imp.old_value) != ctx.norm(f, imp.new_value)
    }
    applies = (
        when.always
        or ctx.case.request.request_type in when.request_types
        or bool(touched & set(when.fields_changed_any))
    )
    if not applies:
        return EvalOutput(status="NOT_APPLICABLE")
    raw = ctx.case.evidence.get(rule.indicator)
    present = raw is True
    actual = "present" if present else ("not provided (false)" if raw is False else "absent")
    values = ctx.base_values(rule.id) | {
        "field": rule.indicator, "field_label": rule.indicator_label, "indicator": rule.indicator,
        "indicator_label": rule.indicator_label, "expected": "present", "actual": actual,
    }
    return EvalOutput(
        checks=1,
        drafts=[
            Draft(
                field=f"evidence.{rule.indicator}",
                expected_value="present",
                expected_source=f"Rule config {rule.id} v{rule.version} (evidence policy)",
                actual_value=actual,
                actual_source=ctx.dms_src,
                result=FindingResult.MATCH if present else FindingResult.EXCEPTION,
                exception_type=None if present else ExceptionType.MISSING_EVIDENCE,
                reason=render(rule.match_template if present else rule.reason_template, **values),
            )
        ],
    )


EVALUATORS: dict[str, Callable[..., EvalOutput]] = {
    "request_approved": _request_approved,
    "required": _required,
    "equality": _equality,
    "authorized_scope": _authorized_scope,
    "source_consistency": _source_consistency,
    "evidence_present": _evidence_present,
}
