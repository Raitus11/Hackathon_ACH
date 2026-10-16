"""AC2: all five seeded scenarios produce their predefined expected outcomes (end to end)."""

from __future__ import annotations

import pytest

from app.engine import evaluate
from app.ingest import build_case
from app.models import FindingResult

SCENARIO_IDS = ["S1", "S2", "S3", "S4", "S5"]


def _exception_set(result) -> set[tuple[str, str, str]]:
    return {(f.rule_id, f.field, f.exception_type.value) for f in result.findings if f.result is FindingResult.EXCEPTION}


def test_exactly_five_seeded_scenarios(scenarios):
    assert sorted(scenarios) == SCENARIO_IDS


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_engine_matches_expected_outcome(scenario_id, scenarios, baseline_cfg):
    s = scenarios[scenario_id]
    result = evaluate(build_case(s.request, s.change), baseline_cfg, scenario_id=s.id)
    assert result.overall.value == s.expected["overall"]
    assert _exception_set(result) == {(e["rule_id"], e["field"], e["exception_type"]) for e in s.expected["exceptions"]}


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_every_exception_is_fully_explained(scenario_id, scenarios, baseline_cfg):
    """AC3: field, expected, actual, configured rule and reason on every exception. No generic failures."""
    s = scenarios[scenario_id]
    result = evaluate(build_case(s.request, s.change), baseline_cfg)
    for f in result.findings:
        if f.result is FindingResult.EXCEPTION:
            assert f.field and f.field_label
            assert f.expected_source and f.actual_source
            assert f.rule_id and f.rule_version >= 1 and f.rule_description
            assert len(f.reason) > 30 and "{" not in f.reason


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_idempotent_same_inputs_same_config_same_findings(scenario_id, scenarios, baseline_cfg):
    s = scenarios[scenario_id]
    first = evaluate(build_case(s.request, s.change), baseline_cfg)
    second = evaluate(build_case(s.request, s.change), baseline_cfg)
    assert first.run_id != second.run_id
    assert first.findings_digest == second.findings_digest
    assert first.findings == second.findings


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenarios_run_through_api(scenario_id, client, scenarios):
    """AC1: request + change record -> one overall PASS or EXCEPTION via the same path the UI uses."""
    body = client.post("/api/runs", json={"scenario_id": scenario_id}, headers={"X-Persona-Id": "C-2001"}).json()
    assert body["result"]["overall"] == scenarios[scenario_id].expected["overall"]
    assert body["decision"] is None
