"""Unit tests: one block per configured rule type."""

from __future__ import annotations

from app.engine import evaluate
from app.ingest import build_case
from app.models import FindingResult, Outcome

from conftest import make_inputs


def run(cfg, **kwargs):
    req, chg = make_inputs(**kwargs)
    return evaluate(build_case(req, chg), cfg)


def exceptions(result):
    return [(f.rule_id, f.field, f.exception_type.value) for f in result.findings if f.result is FindingResult.EXCEPTION]


# request_approved -------------------------------------------------------------

def test_request_not_approved_is_exception(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b@x.example", "a@x.example")},
            status="PENDING")
    assert ("REQ-001", "request.status", "REQUEST_NOT_APPROVED") in exceptions(r)
    f = next(f for f in r.findings if f.rule_id == "REQ-001")
    assert f.actual_value == "PENDING" and "APPROVED" in f.expected_value


# required ---------------------------------------------------------------------

def test_absent_requested_field_is_missing(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example", "company_name": "New Co"},
            tnal={"company_name": ("Old Co", "New Co")})
    assert exceptions(r) == [("FLD-001", "contact_email", "MISSING_FIELD")]


def test_blank_value_is_missing_and_not_double_reported(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b@x.example", "   ")})
    assert exceptions(r) == [("FLD-001", "contact_email", "MISSING_FIELD")]
    f = r.findings[[x.rule_id for x in r.findings].index("FLD-001")]
    assert f.expected_value == "a@x.example" and f.actual_value == "   "
    assert "<blank>" in f.reason


# equality ---------------------------------------------------------------------

def test_equality_mismatch_shows_expected_actual_and_sources(baseline_cfg):
    r = run(baseline_cfg, requested={"daily_debit_limit": "250000.00"}, tnal={"daily_debit_limit": ("1", "2500000.00")})
    f = next(f for f in r.findings if f.result is FindingResult.EXCEPTION)
    assert (f.rule_id, f.rule_version, f.exception_type.value) == ("FLD-002", 1, "MISMATCH")
    assert (f.expected_value, f.actual_value) == ("250000.00", "2500000.00")
    assert "ServiceNow" in f.expected_source and "TNAL" in f.actual_source
    assert "2500000.00" in f.reason and "250000.00" in f.reason


def test_equality_uses_configured_normalisation(baseline_cfg):
    r = run(baseline_cfg,
            requested={"daily_debit_limit": "250,000", "contact_email": " AP@X.example ", "allowed_sec_codes": "PPD, ccd"},
            tnal={"daily_debit_limit": ("1", "250000.00"), "contact_email": ("o", "ap@x.example"),
                  "allowed_sec_codes": ("CCD", "CCD,PPD")})
    assert r.overall is Outcome.PASS


# authorized_scope -------------------------------------------------------------

def test_unrequested_change_is_unauthorized(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"},
            tnal={"contact_email": ("b@x.example", "a@x.example"), "allowed_sec_codes": ("CCD", "CCD,WEB")})
    assert exceptions(r) == [("AUT-001", "allowed_sec_codes", "UNAUTHORIZED_CHANGE")]
    f = next(f for f in r.findings if f.rule_id == "AUT-001")
    assert (f.expected_value, f.actual_value) == ("CCD", "CCD,WEB")


def test_unchanged_row_is_not_unauthorized(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"},
            tnal={"contact_email": ("b@x.example", "a@x.example"), "company_name": ("Same Co", "Same Co")})
    assert r.overall is Outcome.PASS


# source_consistency -----------------------------------------------------------

def test_gps_disagreeing_with_tnal_is_exception(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b@x.example", "a@x.example")},
            gps={"contact_email": "z@x.example"})
    assert exceptions(r) == [("GPS-001", "contact_email", "SOURCE_INCONSISTENT")]


def test_field_missing_from_gps_is_exception(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b@x.example", "a@x.example")},
            gps={})
    assert exceptions(r) == [("GPS-001", "contact_email", "SOURCE_INCONSISTENT")]


# evidence_present -------------------------------------------------------------

def test_absent_required_evidence_is_exception(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b@x.example", "a@x.example")},
            evidence={})
    assert exceptions(r) == [("EVD-001", "evidence.signed_authorization_form", "MISSING_EVIDENCE")]
    assert next(f for f in r.findings if f.rule_id == "EVD-001").actual_value == "absent"


def test_evidence_rule_not_applicable_for_other_request_type(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b@x.example", "a@x.example")},
            evidence={}, request_type="CONTACT_UPDATE")
    status = {e.rule_id: e.status for e in r.rule_evaluations}
    assert status["EVD-001"] == "NOT_APPLICABLE" and r.overall is Outcome.PASS


def test_disabled_rule_is_reported_not_evaluated(baseline_cfg):
    r = run(baseline_cfg, requested={"settlement_routing_number": "990000017"},
            tnal={"settlement_routing_number": ("990000125", "990000017")})
    assert {e.rule_id: e.status for e in r.rule_evaluations}["EVD-002"] == "DISABLED"


# engine guarantees ------------------------------------------------------------

def test_result_has_no_approval_field_and_is_immutable(baseline_cfg):
    r = run(baseline_cfg, requested={"contact_email": "a@x.example"}, tnal={"contact_email": ("b", "a@x.example")})
    assert not any("approv" in name for name in r.model_dump())
    assert "not an approval" in r.decision_support_notice
    import pytest
    with pytest.raises(Exception):
        r.overall = Outcome.EXCEPTION  # type: ignore[misc]
    with pytest.raises(Exception):
        r.findings[0].reason = "edited"  # type: ignore[misc]
