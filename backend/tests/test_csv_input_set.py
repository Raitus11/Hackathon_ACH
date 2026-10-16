"""CSV input set (team export, 4 files) -> canonical request/change -> same pipeline and rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.csv_ingest import build_batch, load_mapping
from app.engine import evaluate
from app.ingest import IngestError, build_case
from app.models import FindingResult

REPO = Path(__file__).resolve().parents[2]
CSV_DIR = REPO / "data" / "csv_input_set"
MAPPING = load_mapping(REPO / "config" / "csv_mapping.yaml")

EXPECTED = {
    "REQ-1001": ("PASS", set()),
    "REQ-1002": ("EXCEPTION", {("FLD-002", "settlement_routing_number", "MISMATCH")}),
    "REQ-1003": ("EXCEPTION", {("FLD-001", "settlement_routing_number", "MISSING_FIELD")}),
    "REQ-1004": ("EXCEPTION", {("AUT-001", "settlement_routing_number", "UNAUTHORIZED_CHANGE")}),
    "REQ-1005": ("EXCEPTION", {("EVD-003", "evidence.secondary_approval_evidence", "MISSING_EVIDENCE")}),
}


def _files(overrides: dict[str, bytes] | None = None) -> list[tuple[str, bytes]]:
    files = {p.name: p.read_bytes() for p in sorted(CSV_DIR.glob("*.csv"))}
    files.update(overrides or {})
    return list(files.items())


def _exceptions(result) -> set[tuple[str, str, str]]:
    return {(f.rule_id, f.field, f.exception_type.value) for f in result.findings if f.result is FindingResult.EXCEPTION}


@pytest.mark.parametrize("request_id", sorted(EXPECTED))
def test_csv_scenarios_match_expected(request_id, baseline_cfg):
    batch = build_batch(_files(), MAPPING)
    case = next(c for c in batch.cases if c.request_id == request_id)
    result = evaluate(build_case(case.request, case.implemented_change), baseline_cfg)
    overall, exceptions = EXPECTED[request_id]
    assert result.overall.value == overall
    assert _exceptions(result) == exceptions


def test_clean_csv_request_normalizes_codes_zeros_and_flags(baseline_cfg):
    batch = build_batch(_files(), MAPPING)
    assert batch.warnings == []
    case = next(c for c in batch.cases if c.request_id == "REQ-1001")
    # TNAL export drops the routing number's leading zero and stores delivery method as a code.
    tnal = {t["field"]: t for t in case.implemented_change["tnal_entries"]}
    assert tnal["settlement_routing_number"]["old_value"] == "11000015"
    assert tnal["statement_delivery_method"]["new_value"] == "1"
    result = evaluate(build_case(case.request, case.implemented_change), baseline_cfg)
    rules = {e.rule_id: e.status for e in result.rule_evaluations}
    assert rules["GPS-001"] == "NOT_APPLICABLE"  # no GPS report in the CSV input set
    assert rules["EVD-001"] == "NOT_APPLICABLE"  # request type MAINTENANCE, not ACCOUNT_MAINTENANCE
    assert rules["EVD-003"] == "EVALUATED"
    assert case.request["evidence_required_for"] == ["settlement_routing_number"]


def test_mismatch_finding_is_explained(baseline_cfg):
    case = next(c for c in build_batch(_files(), MAPPING).cases if c.request_id == "REQ-1002")
    result = evaluate(build_case(case.request, case.implemented_change), baseline_cfg)
    [f] = [f for f in result.findings if f.result is FindingResult.EXCEPTION]
    assert (f.expected_value, f.actual_value) == ("121000248", "91000019")
    assert "TNAL-4" in f.actual_source and "{" not in f.reason


def test_missing_file_and_missing_column_are_structured_errors():
    files = [f for f in _files() if not f[0].startswith("request_document")]
    with pytest.raises(IngestError) as e:
        build_batch(files, MAPPING)
    assert e.value.code == "CSV_FILES_INVALID"

    audit = (CSV_DIR / "tnal_audit_event.csv").read_bytes().replace(b"canonical_field", b"cf")
    with pytest.raises(IngestError) as e:
        build_batch(_files({"tnal_audit_event.csv": audit}), MAPPING)
    assert e.value.code == "CSV_COLUMNS_MISSING" and "canonical_field" in e.value.message


def test_excel_bom_and_download_suffix_are_tolerated():
    name, data = next(f for f in _files() if f[0].startswith("request_document"))
    files = [f for f in _files() if f[0] != name] + [("request_document (1).csv", b"\xef\xbb\xbf" + data)]
    assert len(build_batch(files, MAPPING).cases) == 5


def test_unmapped_field_code_is_warned_not_dropped():
    chg = (CSV_DIR / "customer_request_change.csv").read_bytes().replace(b"ACH_HOLD_IND", b"NEW_FLAG")
    batch = build_batch(_files({"customer_request_change.csv": chg}), MAPPING)
    assert any("NEW_FLAG" in w for w in batch.warnings)
    case = next(c for c in batch.cases if c.request_id == "REQ-1001")
    assert {"field": "new_flag", "requested_value": "Y"} in case.request["requested_changes"]


def test_batch_api_runs_every_request_and_links_runs(client):
    files = [{"name": n, "content": d.decode("utf-8")} for n, d in _files()]
    resp = client.post("/api/csv/batches", json={"files": files}, headers={"X-Persona-Id": "C-2001"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    s = body["summary"]
    assert (s["requests"], s["pass"], s["exception"], s["rejected"]) == (5, 1, 4, 0)
    by_id = {i["request_id"]: i for i in body["items"]}
    assert by_id["REQ-1004"]["exceptions"][0]["rule_id"] == "AUT-001"

    run = client.get(f"/api/runs/{by_id['REQ-1002']['run_id']}").json()
    assert run["source"] == {"kind": "CSV_BATCH", "batch_id": body["batch_id"], "request_id": "REQ-1002"}
    assert run["inputs"]["implemented_change"]["gps_report_available"] is False

    # Same checker workflow as any other run.
    dec = client.post(f"/api/runs/{by_id['REQ-1001']['run_id']}/decision", headers={"X-Persona-Id": "C-2001"},
                      json={"decision": "APPROVE", "comment": "Clean match per CSV input set."})
    assert dec.status_code == 200, dec.text

    assert client.get(f"/api/csv/batches/{body['batch_id']}").json()["batch_id"] == body["batch_id"]
    assert client.get("/api/csv/batches").json()[0]["batch_id"] == body["batch_id"]
    assert client.get("/api/csv/batches/../../etc").status_code == 404
    events = [e["event_type"] for e in client.get("/api/audit").json()]
    assert "CSV_BATCH_VALIDATED" in events


def test_batch_api_rejects_incomplete_set(client):
    files = [{"name": n, "content": d.decode("utf-8")} for n, d in _files()][:2]
    resp = client.post("/api/csv/batches", json={"files": files})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CSV_FILES_INVALID"


def test_csv_schema_endpoint(client):
    body = client.get("/api/csv/schema").json()
    assert set(body["files"]) == {"customer_maintenance_request", "customer_request_change",
                                  "request_document", "tnal_audit_event"}
    assert "SETTLEMENT_RT" in body["field_codes"]["settlement_routing_number"]
