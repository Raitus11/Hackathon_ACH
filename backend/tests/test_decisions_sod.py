"""AC5 / AC6: human approval boundary, maker self-approval blocked, traceability."""

from __future__ import annotations

from conftest import make_inputs

MAKER = {"X-Persona-Id": "P-1001"}       # implemented S1, S2, S4
OTHER_MAKER = {"X-Persona-Id": "P-1002"}
CHECKER = {"X-Persona-Id": "C-2001"}


def _run(client, scenario_id):
    return client.post("/api/runs", json={"scenario_id": scenario_id}, headers=CHECKER).json()["result"]


def test_maker_cannot_decide_own_change(client):
    run = _run(client, "S2")
    resp = client.post(f"/api/runs/{run['run_id']}/decision", headers=MAKER,
                       json={"ai_review_confirmed": True, "decision": "APPROVE", "comment": "Looks fine to me", "acknowledge_exceptions": True})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "SELF_APPROVAL_BLOCKED"
    events = client.get("/api/audit", params={"run_id": run["run_id"]}).json()
    assert events[0]["event_type"] == "DECISION_BLOCKED"


def test_maker_cannot_decide_even_others_change(client):
    run = _run(client, "S2")  # implemented by P-1001
    resp = client.post(f"/api/runs/{run['run_id']}/decision", headers=OTHER_MAKER,
                       json={"ai_review_confirmed": True, "decision": "INVESTIGATE", "comment": "Checking this"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ROLE_NOT_PERMITTED"


def test_unknown_persona_rejected(client):
    run = _run(client, "S1")
    resp = client.post(f"/api/runs/{run['run_id']}/decision", json={"ai_review_confirmed": True, "decision": "APPROVE", "comment": "ok ok"})
    assert resp.status_code == 401


def test_pass_is_not_approved_until_checker_decides(client):
    run = _run(client, "S1")
    assert run["overall"] == "PASS"
    assert client.get(f"/api/runs/{run['run_id']}").json()["decision"] is None
    resp = client.post(f"/api/runs/{run['run_id']}/decision", headers=CHECKER,
                       json={"ai_review_confirmed": True, "decision": "APPROVE", "comment": "Values and evidence verified."})
    assert resp.status_code == 200
    d = resp.json()["decision"]
    assert (d["decision"], d["actor_id"], d["engine_outcome"]) == ("APPROVE", "C-2001", "PASS")


def test_checker_investigates_exception(client):
    run = _run(client, "S2")
    resp = client.post(f"/api/runs/{run['run_id']}/decision", headers=CHECKER,
                       json={"ai_review_confirmed": True, "decision": "INVESTIGATE", "comment": "Debit limit keyed 10x. Returning to processor."})
    assert resp.status_code == 200 and resp.json()["decision"]["decision"] == "INVESTIGATE"


def test_approving_an_exception_requires_acknowledgement_and_justification(client):
    run = _run(client, "S2")
    url = f"/api/runs/{run['run_id']}/decision"
    r1 = client.post(url, headers=CHECKER, json={"ai_review_confirmed": True, "decision": "APPROVE", "comment": "fine fine fine fine fine"})
    assert r1.json()["error"]["code"] == "EXCEPTIONS_NOT_ACKNOWLEDGED"
    r2 = client.post(url, headers=CHECKER, json={"ai_review_confirmed": True, "decision": "APPROVE", "comment": "ok ok", "acknowledge_exceptions": True})
    assert r2.json()["error"]["code"] == "JUSTIFICATION_TOO_SHORT"
    r3 = client.post(url, headers=CHECKER, json={"ai_review_confirmed": True, "decision": "APPROVE", "acknowledge_exceptions": True,
                                                 "comment": "Customer confirmed 2.5M limit by callback; request form typo."})
    assert r3.status_code == 200 and r3.json()["decision"]["acknowledged_exceptions"] is True


def test_decision_is_write_once(client):
    run = _run(client, "S3")
    url = f"/api/runs/{run['run_id']}/decision"
    assert client.post(url, headers=CHECKER, json={"ai_review_confirmed": True, "decision": "INVESTIGATE", "comment": "Email blank."}).status_code == 200
    again = client.post(url, headers=CHECKER, json={"ai_review_confirmed": True, "decision": "INVESTIGATE", "comment": "Again please"})
    assert again.status_code == 409


def test_comment_is_mandatory(client):
    run = _run(client, "S1")
    resp = client.post(f"/api/runs/{run['run_id']}/decision", headers=CHECKER, json={"ai_review_confirmed": True, "decision": "APPROVE", "comment": ""})
    assert resp.status_code == 422


def test_run_is_traceable_in_audit_and_evidence(client):
    run = _run(client, "S4")
    client.post(f"/api/runs/{run['run_id']}/decision", headers=CHECKER,
                json={"ai_review_confirmed": True, "decision": "INVESTIGATE", "comment": "SEC codes changed without request."})
    events = client.get("/api/audit", params={"run_id": run["run_id"]}).json()
    completed = next(e for e in events if e["event_type"] == "VALIDATION_RUN_COMPLETED")["payload"]
    assert completed["config_sha256"] == run["config_hash"]
    assert completed["request_id"] == "REQ-2026-10-0004" and completed["exception_rules"] == ["AUT-001"]

    pack = client.get(f"/api/runs/{run['run_id']}/evidence").json()
    assert pack["configuration"]["sha256"] == run["config_hash"]
    assert "AUT-001" in pack["configuration"]["content"]
    assert pack["checker_decision"]["decision"] == "INVESTIGATE"
    assert "SYNTHETIC" in pack["label"]
    md = client.get(f"/api/runs/{run['run_id']}/evidence", params={"format": "md"}).text
    assert "UNAUTHORIZED_CHANGE" in md and "INVESTIGATE" in md


def test_ad_hoc_upload_and_record_matching(client):
    req, chg = make_inputs(requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b", "a@x.example")})
    ok = client.post("/api/runs", json={"request": req, "implemented_change": chg})
    assert ok.status_code == 200 and ok.json()["result"]["scenario_id"] is None
    chg["request_id"] = "REQ-OTHER"
    bad = client.post("/api/runs", json={"request": req, "implemented_change": chg})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "RECORD_MATCH_FAILED"


def test_schema_errors_are_structured(client):
    req, chg = make_inputs(requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b", "a@x.example")})
    del req["status"]
    resp = client.post("/api/runs", json={"request": req, "implemented_change": chg})
    err = resp.json()["error"]
    assert err["code"] == "SCHEMA_VALIDATION_FAILED"
    assert any(d["location"] == "status" and d["source"] == "request" for d in err["details"])
