"""Seeded-scenario suite (AC2 / FAQ Q48): runs all five scenarios through the deterministic engine
and compares each result with its predefined expected outcome. Read-only, no runs stored."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import LoadedConfig
from .engine import evaluate
from .explain import show
from .ingest import build_case
from .models import FindingResult
from .scenarios import Scenario


def run_suite(scenarios: list[Scenario], cfg: LoadedConfig) -> dict[str, Any]:
    rows = []
    for s in scenarios:
        case = build_case(s.request, s.change)
        result = evaluate(case, cfg, scenario_id=s.id, run_id=f"SUITE-{s.id}")
        actual = sorted((f.rule_id, f.field, f.exception_type.value) for f in result.findings
                        if f.result is FindingResult.EXCEPTION and f.exception_type)
        expected = sorted((e["rule_id"], e["field"], e["exception_type"]) for e in s.expected.get("exceptions", []))
        passed = result.overall.value == s.expected.get("overall") and actual == expected
        rows.append({
            "scenario_id": s.id, "name": s.name, "seeded_condition": s.seeded_condition,
            "organizer_expected_outcome": s.organizer_expected_outcome,
            "expected_overall": s.expected.get("overall"), "actual_overall": result.overall.value,
            "expected_exceptions": [list(e) for e in expected], "actual_exceptions": [list(a) for a in actual],
            "status": "PASS" if passed else "FAIL",
            "findings_digest": result.findings_digest[:16],
            "exception_details": [
                {"field": f.field_label, "expected": show(f.expected_value), "actual": show(f.actual_value),
                 "rule": f"{f.rule_id} v{f.rule_version}"}
                for f in result.findings if f.result is FindingResult.EXCEPTION
            ],
            "expectation_baseline": s.expected.get("config_baseline"),
        })
    passed = sum(r["status"] == "PASS" for r in rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"file": cfg.path.name, "version": cfg.ruleset.ruleset.version, "short_hash": cfg.short_hash},
        "summary": {"total": len(rows), "passed": passed},
        "scenarios": rows,
        "notice": "Expected outcomes are defined against the baseline rule file v1.0.0. If the active rule file "
                  "has been edited (AC4 demo), a scenario may now differ: that is the configuration change working.",
    }
