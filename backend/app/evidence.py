"""Lightweight validation summary export ("evidence pack"). Prototype artifact, not a records-
management implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .explain import show
from .models import DecisionRecord, FindingResult, MaintenanceCase, ValidationResult

LABEL = "SYNTHETIC DATA · SIMULATED SYSTEMS · PROTOTYPE — not production evidence, not an approval record"


def build_pack(
    result: ValidationResult,
    case: MaintenanceCase,
    decision: DecisionRecord | None,
    audit_events: list[dict],
    config_text: str | None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "label": LABEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "control": {"control_id": result.control_id, "ruleset_id": result.ruleset_id},
        "run": {
            "run_id": result.run_id,
            "evaluated_at": result.evaluated_at.isoformat(),
            "engine_outcome": result.overall.value,
            "decision_support_notice": result.decision_support_notice,
            "input_digest": result.input_digest,
            "findings_digest": result.findings_digest,
        },
        "configuration": {
            "file": result.config_file,
            "version": result.config_version,
            "sha256": result.config_hash,
            "content": config_text,
        },
        "inputs": {
            "request": case.request.model_dump(mode="json"),
            "implemented_change": case.change.model_dump(mode="json"),
        },
        "rule_evaluations": [e.model_dump(mode="json") for e in result.rule_evaluations],
        "findings": [f.model_dump(mode="json") for f in result.findings],
        "checker_decision": decision.model_dump(mode="json") if decision else None,
        "agent_pipeline": (extras or {}).get("pipeline", []),
        "ai_assisted_extraction": (extras or {}).get("extraction"),
        "audit_events": audit_events,
    }


def _cell(value: str | None) -> str:
    return show(value).replace("|", "\\|")


def render_markdown(pack: dict[str, Any]) -> str:
    run, cfg = pack["run"], pack["configuration"]
    req = pack["inputs"]["request"]
    chg = pack["inputs"]["implemented_change"]
    decision = pack["checker_decision"]
    lines = [
        "# Validation evidence summary",
        "",
        f"> {pack['label']}",
        "",
        f"- **Control:** {pack['control']['control_id']} ({pack['control']['ruleset_id']})",
        f"- **Run:** {run['run_id']} at {run['evaluated_at']}",
        f"- **Request:** {req['request_id']} · {req['customer_name']} ({req['customer_id']}) · status {req['status']}",
        f"- **Implemented change:** {chg['change_id']} by {chg['implemented_by']} at {chg['implemented_at']}",
        f"- **Configuration:** {cfg['file']} v{cfg['version']} · sha256 `{cfg['sha256']}`",
        f"- **Input digest:** `{run['input_digest']}`",
        f"- **Findings digest:** `{run['findings_digest']}`",
        "",
        f"## Engine outcome: {run['engine_outcome']}",
        "",
        f"_{run['decision_support_notice']}_",
        "",
        "## Findings",
        "",
        "| # | Result | Field | Expected | Actual | Rule | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    ordered = sorted(pack["findings"], key=lambda f: (f["result"] != FindingResult.EXCEPTION.value, f["finding_id"]))
    for f in ordered:
        lines.append(
            f"| {f['finding_id']} | {f['result']}{' · ' + f['exception_type'] if f['exception_type'] else ''} "
            f"| {f['field_label']} | {_cell(f['expected_value'])}<br>_{f['expected_source']}_ "
            f"| {_cell(f['actual_value'])}<br>_{f['actual_source']}_ "
            f"| {f['rule_id']} v{f['rule_version']} | {f['reason'].replace('|', '/')} |"
        )
    lines += ["", "## Rules evaluated", "", "| Rule | Version | Type | Status | Checks | Exceptions |", "|---|---|---|---|---|---|"]
    for e in pack["rule_evaluations"]:
        lines.append(f"| {e['rule_id']} | {e['rule_version']} | {e['rule_type']} | {e['status']} | {e['checks']} | {e['exceptions']} |")
    ext = pack.get("ai_assisted_extraction")
    if ext:
        lines += ["", "## AI-assisted document extraction (advisory, not used by the rule engine)", "",
                  f"_{ext['notice']}_", "",
                  f"- **Status:** {ext['status']} · provider {ext['provider']} ({'SIMULATED' if ext['simulated'] else 'live'}) · "
                  f"model {ext['model']} · cache {ext['cache']}"]
        if ext["fields"]:
            lines += ["", "| Field | Extracted | Confidence | Request | Agreement |", "|---|---|---|---|---|"]
            for f in ext["fields"]:
                lines.append(f"| {f['label']} | {_cell(f['extracted_value'])} | {f['confidence']:.2f} | "
                             f"{_cell(f['request_value'])} | {f['agreement']} |")
    if pack.get("agent_pipeline"):
        lines += ["", "## Agent pipeline", "", "| # | Agent | Kind | Status | ms | Summary |", "|---|---|---|---|---|---|"]
        for s in pack["agent_pipeline"]:
            lines.append(f"| {s['order']} | {s['agent']} | {s['kind']} | {s['status']} | {s['duration_ms']} | "
                         f"{s['summary'].replace('|', '/')} |")
    lines += ["", "## Checker decision (human-approval boundary)", ""]
    if decision:
        lines += [
            f"- **Decision:** {decision['decision']}",
            f"- **By:** {decision['actor_name']} ({decision['actor_id']}, {decision['actor_role']})",
            f"- **At:** {decision['recorded_at']}",
            f"- **Exceptions acknowledged:** {'yes' if decision['acknowledged_exceptions'] else 'n/a'}",
            f"- **AI-extracted values reviewed:** {'yes' if decision.get('ai_review_confirmed') else 'n/a'}",
            f"- **Comment:** {decision['comment']}",
        ]
    else:
        lines.append("_No checker decision recorded yet. The item is not approved._")
    lines += ["", "## Audit events", ""]
    for ev in pack["audit_events"]:
        lines.append(f"- {ev['timestamp']} · {ev['event_type']} · actor {ev.get('actor') or 'system'}")
    lines.append("")
    return "\n".join(lines)
