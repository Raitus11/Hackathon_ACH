"""RBAC and segregation of duties for the checker decision (FAQ Q10, Q38).

Enforced server-side; the UI only mirrors these rules. A simple persona header stands in for
real identity, which is out of scope for the prototype.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import DecisionInput, DocumentExtraction, FindingResult, Persona, ValidationResult


class SodViolation(Exception):
    def __init__(self, code: str, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def load_personas(path: Path) -> dict[str, Persona]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    personas = [Persona.model_validate(p) for p in data.get("personas", [])]
    return {p.id: p for p in personas}


def check_decision_allowed(actor: Persona, result: ValidationResult, decision: DecisionInput,
                           extraction: DocumentExtraction | None = None) -> None:
    # Order matters for the message: self-approval is the control failure we want to name.
    if actor.id == result.implemented_by:
        raise SodViolation(
            "SELF_APPROVAL_BLOCKED",
            f"{actor.name} ({actor.id}) implemented change {result.change_id}. "
            "The maker cannot record a decision on their own work.",
        )
    if actor.role != "CHECKER":
        raise SodViolation(
            "ROLE_NOT_PERMITTED",
            f"{actor.name} has role {actor.role}. Only an independent CHECKER may record Approve or Investigate.",
        )
    if decision.decision.value == "APPROVE" and result.exception_count > 0:
        if not decision.acknowledge_exceptions:
            raise SodViolation(
                "EXCEPTIONS_NOT_ACKNOWLEDGED",
                f"This item has {result.exception_count} open exception(s). Approving requires an explicit "
                "acknowledgement and a justification comment.",
                status=422,
            )
        if len(decision.comment.strip()) < 20:
            raise SodViolation(
                "JUSTIFICATION_TOO_SHORT",
                "Approving despite exceptions requires a justification of at least 20 characters.",
                status=422,
            )
    if extraction is not None and extraction.status == "EXTRACTED" and not decision.ai_review_confirmed:
        raise SodViolation(
            "AI_REVIEW_NOT_CONFIRMED",
            "This item has AI-assisted extracted values. Confirm you reviewed them before recording a decision.",
            status=422,
        )


def open_exception_rules(result: ValidationResult) -> list[str]:
    return [f.rule_id for f in result.findings if f.result is FindingResult.EXCEPTION]
