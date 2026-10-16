"""AC4: change an externally defined rule, rerun, behaviour changes with no code change."""

from __future__ import annotations

from app.config import load_ruleset
from app.engine import evaluate
from app.ingest import build_case

from conftest import SAMPLE_V11


def test_editing_the_live_rule_file_flips_scenario_1(client, tmp_settings):
    first = client.post("/api/runs", json={"scenario_id": "S1"}).json()["result"]
    assert first["overall"] == "PASS"

    # The demo edit: one line in the external YAML. No code is touched.
    text = tmp_settings.rules_path.read_text()
    assert text.count("enabled: false") == 1
    tmp_settings.rules_path.write_text(text.replace("enabled: false", "enabled: true"))

    second = client.post("/api/runs", json={"scenario_id": "S1"}).json()["result"]
    assert second["overall"] == "EXCEPTION"
    [finding] = [f for f in second["findings"] if f["result"] == "EXCEPTION"]
    assert (finding["rule_id"], finding["exception_type"]) == ("EVD-002", "MISSING_EVIDENCE")
    assert second["config_hash"] != first["config_hash"]
    assert second["input_digest"] == first["input_digest"]  # same inputs, different rules


def test_sample_v110_config_matches_documented_change(scenarios):
    v1 = load_ruleset(SAMPLE_V11.parents[1] / "ach_db_next_day.yaml")
    v11 = load_ruleset(SAMPLE_V11)
    s1 = scenarios["S1"]
    case = build_case(s1.request, s1.change)
    a, b = evaluate(case, v1), evaluate(case, v11)
    assert (a.config_version, a.overall.value) == ("1.0.0", "PASS")
    assert (b.config_version, b.overall.value) == ("1.1.0", "EXCEPTION")
    evd = next(f for f in b.findings if f.rule_id == "EVD-002")
    assert evd.rule_version == 2
    # Every other scenario is unaffected by the tightened evidence rule.
    for sid in ("S2", "S3", "S4", "S5"):
        s = scenarios[sid]
        c = build_case(s.request, s.change)
        assert evaluate(c, v1).overall == evaluate(c, v11).overall


def test_invalid_edit_is_rejected_with_structured_error(client, tmp_settings):
    text = tmp_settings.rules_path.read_text()
    tmp_settings.rules_path.write_text(text.replace("type: equality", "type: equalitee"))
    resp = client.post("/api/runs", json={"scenario_id": "S1"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONFIG_INVALID"
