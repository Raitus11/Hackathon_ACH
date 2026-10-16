"""Secure config loading: safe YAML, schema validation, template whitelisting."""

from __future__ import annotations

import pytest

from app.config import ConfigError, load_ruleset

from conftest import BASELINE_RULES


def _write(tmp_path, text):
    p = tmp_path / "r.yaml"
    p.write_text(text)
    return p


def test_baseline_loads_with_hash(baseline_cfg):
    assert baseline_cfg.ruleset.ruleset.control_id == "C-247489"
    assert len(baseline_cfg.sha256) == 64
    assert {r.type for r in baseline_cfg.ruleset.rules} == {
        "request_approved", "required", "equality", "authorized_scope", "source_consistency", "evidence_present"}


def test_python_object_tags_are_refused(tmp_path):
    with pytest.raises(ConfigError):
        load_ruleset(_write(tmp_path, "!!python/object/apply:os.system ['echo pwned']\n"))


def test_malformed_yaml_reports_line(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_ruleset(_write(tmp_path, "ruleset: [unclosed\n"))
    assert "YAML" in exc.value.message


def test_unknown_placeholder_rejected(tmp_path):
    text = BASELINE_RULES.read_text().replace("request specifies {expected}", "request specifies {expected.__class__}")
    with pytest.raises(ConfigError) as exc:
        load_ruleset(_write(tmp_path, text))
    assert any("placeholder" in d["message"] for d in exc.value.details)


def test_duplicate_rule_ids_rejected(tmp_path):
    text = BASELINE_RULES.read_text().replace("id: FLD-002", "id: FLD-001")
    with pytest.raises(ConfigError) as exc:
        load_ruleset(_write(tmp_path, text))
    assert any("duplicate" in d["message"] for d in exc.value.details)


def test_unknown_keys_rejected(tmp_path):
    text = BASELINE_RULES.read_text().replace("    severity: HIGH\n", "    severity: HIGH\n    auto_approve: true\n", 1)
    with pytest.raises(ConfigError):
        load_ruleset(_write(tmp_path, text))
