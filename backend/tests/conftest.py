from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.config import load_ruleset  # noqa: E402
from app.scenarios import load_scenarios  # noqa: E402
from app.settings import Settings  # noqa: E402

BASELINE_RULES = REPO / "config" / "rules" / "ach_db_next_day.yaml"
SAMPLE_V11 = REPO / "config" / "rules" / "samples" / "ach_db_next_day.v1.1.0.yaml"
SCENARIOS_DIR = REPO / "data" / "scenarios"


@pytest.fixture
def baseline_cfg():
    return load_ruleset(BASELINE_RULES)


@pytest.fixture
def scenarios():
    return {s.id: s for s in load_scenarios(SCENARIOS_DIR)}


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    """Isolated runtime and a private, editable copy of the rule file."""
    rules = tmp_path / "rules.yaml"
    shutil.copy(BASELINE_RULES, rules)
    return Settings(
        rules_path=rules,
        llm_config_path=REPO / "config" / "llm.yaml",
        personas_path=REPO / "config" / "personas.yaml",
        scenarios_dir=SCENARIOS_DIR,
        runtime_dir=tmp_path / "runtime",
        frontend_dist=tmp_path / "no-ui",
        env_path=tmp_path / ".env",
    )


@pytest.fixture
def client(tmp_settings):
    from fastapi.testclient import TestClient

    from app.api import create_app

    return TestClient(create_app(tmp_settings))


def make_inputs(requested: dict[str, str], tnal: dict[str, tuple[str | None, str | None]],
                gps: dict[str, str | None] | None = None, evidence: dict[str, bool] | None = None,
                status: str = "APPROVED", request_type: str = "ACCOUNT_MAINTENANCE"):
    """Small synthetic request/change pair for unit tests."""
    request = {
        "request_id": "REQ-T-1", "customer_id": "CUST-T", "customer_name": "Test Co (synthetic)",
        "request_type": request_type, "status": status, "submitted_by": "U-1", "approved_by": "S-1",
        "requested_changes": [{"field": f, "requested_value": v} for f, v in requested.items()],
        "evidence": {"signed_authorization_form": True} if evidence is None else evidence,
    }
    change = {
        "change_id": "CHG-T-1", "request_id": "REQ-T-1", "customer_id": "CUST-T", "implemented_by": "P-1001",
        "implemented_at": "2026-10-15T10:00:00Z",
        "tnal_entries": [
            {"record_id": f"TNAL-{i}", "customer_id": "CUST-T", "field": f, "old_value": old, "new_value": new,
             "changed_by": "P-1001", "changed_at": f"2026-10-15T10:00:{i:02d}Z"}
            for i, (f, (old, new)) in enumerate(tnal.items())
        ],
        "gps_changes": [{"field": f, "new_value": v} for f, v in
                        (gps if gps is not None else {f: n for f, (_, n) in tnal.items()}).items()],
    }
    return copy.deepcopy(request), copy.deepcopy(change)
