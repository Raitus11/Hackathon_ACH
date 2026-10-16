"""Differentiators: rule version comparison / scenario replay, simulated exception queue,
seeded-scenario suite and prototype metrics."""

from __future__ import annotations

import shutil

from conftest import SAMPLE_V11

CHECKER = {"X-Persona-Id": "C-2001"}
MAKER = {"X-Persona-Id": "P-1001"}


def _with_sample(tmp_settings):
    samples = tmp_settings.rules_path.parent / "samples"
    samples.mkdir(exist_ok=True)
    shutil.copy(SAMPLE_V11, samples / SAMPLE_V11.name)
    return f"sample:{SAMPLE_V11.name}"


def test_configs_lists_active_and_sample(client, tmp_settings):
    key = _with_sample(tmp_settings)
    keys = [c["key"] for c in client.get("/api/configs").json()]
    assert keys[0] == "active" and key in keys


def test_compare_shows_new_exception_for_same_inputs(client, tmp_settings):
    key = _with_sample(tmp_settings)
    out = client.post("/api/compare", headers=CHECKER,
                      json={"scenario_id": "S1", "baseline": "active", "candidate": key}).json()
    assert out["baseline_result"]["overall"] == "PASS"
    assert out["candidate_result"]["overall"] == "EXCEPTION"
    assert out["outcome_changed"] is True
    changed = [f for f in out["findings"] if f["change"] != "UNCHANGED"]
    assert changed and changed[0]["rule_id"] == "EVD-002" and changed[0]["change"] in ("NEW_EXCEPTION", "CHECK_ADDED")
    diff = {d["rule_id"]: d for d in out["rule_diffs"]}
    attrs = {a["name"]: a for a in diff["EVD-002"]["attributes"]}
    assert attrs["enabled"]["before"] is False and attrs["enabled"]["after"] is True
    events = client.get("/api/audit").json()
    assert events[0]["event_type"] == "RULE_VERSION_COMPARISON"


def test_compare_same_config_is_identical(client):
    out = client.post("/api/compare", headers=CHECKER,
                      json={"scenario_id": "S2", "baseline": "active", "candidate": "active"}).json()
    assert out["outcome_changed"] is False and out["changed_findings"] == 0 and out["rule_diffs"] == []
    assert out["baseline_result"]["findings_digest"] == out["candidate_result"]["findings_digest"]


def test_replay_against_snapshot_after_rule_edit(client, tmp_settings):
    """AC4 replay: run, edit the external file, then compare the previous run's config snapshot with the edit."""
    run = client.post("/api/runs", json={"scenario_id": "S1"}, headers=CHECKER).json()["result"]
    path = tmp_settings.rules_path
    path.write_text(path.read_text().replace("enabled: false", "enabled: true", 1))
    snap_key = f"snapshot:{run['config_hash']}"
    assert snap_key in [c["key"] for c in client.get("/api/configs").json()]
    out = client.post("/api/compare", headers=CHECKER,
                      json={"scenario_id": "S1", "baseline": snap_key, "candidate": "active"}).json()
    assert (out["baseline_result"]["overall"], out["candidate_result"]["overall"]) == ("PASS", "EXCEPTION")


def test_compare_unknown_config_rejected(client):
    resp = client.post("/api/compare", json={"scenario_id": "S1", "baseline": "active", "candidate": "sample:nope.yaml"})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "CONFIG_INVALID"


def test_investigate_routes_to_simulated_queue_and_approve_does_not(client):
    s2 = client.post("/api/runs", json={"scenario_id": "S2"}, headers=CHECKER).json()["result"]
    resp = client.post(f"/api/runs/{s2['run_id']}/decision", headers=CHECKER,
                       json={"decision": "INVESTIGATE", "comment": "Debit limit differs", "ai_review_confirmed": True}).json()
    assert resp["routed"]["routed_to"] == "P-1001" and resp["routed"]["simulated"] is True
    s1 = client.post("/api/runs", json={"scenario_id": "S1"}, headers=CHECKER).json()["result"]
    resp1 = client.post(f"/api/runs/{s1['run_id']}/decision", headers=CHECKER,
                        json={"decision": "APPROVE", "comment": "All matched", "ai_review_confirmed": True}).json()
    assert resp1["routed"] is None
    queue = client.get("/api/queue").json()
    assert "SIMULATED" in queue["label"]
    assert [i["run_id"] for i in queue["items"]] == [s2["run_id"]]
    item = queue["items"][0]
    assert item["exceptions"][0]["rule_id"] == "FLD-002" and item["status"] == "AWAITING_PROCESSOR_CORRECTION"


def test_scenario_suite_all_five_pass_on_baseline(client):
    out = client.post("/api/scenarios/suite", headers=CHECKER).json()
    assert out["summary"] == {"total": 5, "passed": 5}
    assert [r["status"] for r in out["scenarios"]] == ["PASS"] * 5


def test_metrics_counts_runs_decisions_and_blocks(client):
    s2 = client.post("/api/runs", json={"scenario_id": "S2"}, headers=CHECKER).json()["result"]
    client.post(f"/api/runs/{s2['run_id']}/decision", headers=MAKER,
                json={"decision": "APPROVE", "comment": "Looks fine to me", "acknowledge_exceptions": True, "ai_review_confirmed": True})
    client.post(f"/api/runs/{s2['run_id']}/decision", headers=CHECKER,
                json={"decision": "INVESTIGATE", "comment": "Debit limit differs", "ai_review_confirmed": True})
    m = client.get("/api/metrics").json()
    assert m["runs"] == 1 and m["exception"] == 1 and m["exceptions_by_rule"] == {"FLD-002": 1}
    assert m["self_approval_blocked"] == 1 and m["decisions"]["INVESTIGATE"] == 1 and m["routed_to_queue"] == 1
