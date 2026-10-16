"""Rule version comparison and scenario replay (organizer differentiators).

Replays the SAME inputs through the deterministic engine under two rule configurations and
reports which findings changed. Read-only: no run is stored, no decision is possible, and the
engine is the same code path used for real runs. AI extraction is not involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigError, LoadedConfig, load_ruleset
from .engine import evaluate
from .ingest import build_case
from .models import FindingResult, MaintenanceCase, ValidationResult


@dataclass(frozen=True)
class ConfigOption:
    key: str
    kind: str  # ACTIVE | SAMPLE | SNAPSHOT
    label: str
    path: Path


def list_config_options(active: Path, samples_dir: Path, snapshots_dir: Path,
                        recent_hashes: list[tuple[str, str, str]]) -> list[ConfigOption]:
    """recent_hashes: (sha256, run_id, evaluated_at) of recent runs, newest first."""
    options = [ConfigOption("active", "ACTIVE", f"Active rule file · {active.name}", active)]
    if samples_dir.is_dir():
        for p in sorted(samples_dir.glob("*.yaml")):
            options.append(ConfigOption(f"sample:{p.name}", "SAMPLE", f"Sample rule config · {p.name}", p))
    seen: set[str] = set()
    for sha, run_id, at in recent_hashes:
        snap = snapshots_dir / f"{sha}.yaml"
        if sha in seen or not snap.exists():
            continue
        seen.add(sha)
        options.append(ConfigOption(f"snapshot:{sha}", "SNAPSHOT", f"Config used by {run_id} ({at[11:19]} UTC)", snap))
        if len(seen) >= 6:
            break
    return options


def resolve(key: str, options: list[ConfigOption]) -> LoadedConfig:
    for o in options:
        if o.key == key:
            return load_ruleset(o.path)
    raise ConfigError(f"Unknown rule configuration '{key}'")


def describe(cfg: LoadedConfig, key: str, options: list[ConfigOption]) -> dict[str, Any]:
    opt = next((o for o in options if o.key == key), None)
    return {"key": key, "kind": opt.kind if opt else "UNKNOWN", "label": opt.label if opt else key,
            "version": cfg.ruleset.ruleset.version, "sha256": cfg.sha256, "short_hash": cfg.short_hash}


def _rule_diffs(a: LoadedConfig, b: LoadedConfig) -> list[dict[str, Any]]:
    ra = {r.id: r.model_dump() for r in a.ruleset.rules}
    rb = {r.id: r.model_dump() for r in b.ruleset.rules}
    out: list[dict[str, Any]] = []
    for rid in sorted(set(ra) | set(rb)):
        if rid not in ra:
            out.append({"rule_id": rid, "change": "ADDED", "attributes": []})
        elif rid not in rb:
            out.append({"rule_id": rid, "change": "REMOVED", "attributes": []})
        else:
            attrs = [{"name": k, "before": ra[rid].get(k), "after": rb[rid].get(k)}
                     for k in sorted(set(ra[rid]) | set(rb[rid])) if ra[rid].get(k) != rb[rid].get(k)]
            if attrs:
                out.append({"rule_id": rid, "change": "MODIFIED", "attributes": attrs})
    return out


def _finding_rows(ra: ValidationResult, rb: ValidationResult) -> list[dict[str, Any]]:
    fa = {(f.rule_id, f.field): f for f in ra.findings}
    fb = {(f.rule_id, f.field): f for f in rb.findings}
    keys = list(dict.fromkeys([*fa.keys(), *fb.keys()]))
    rows = []
    for key in keys:
        a, b = fa.get(key), fb.get(key)
        res_a = a.result.value if a else "NOT_CHECKED"
        res_b = b.result.value if b else "NOT_CHECKED"
        if res_a == res_b:
            change = "UNCHANGED"
        elif res_b == "EXCEPTION":
            change = "NEW_EXCEPTION"
        elif res_a == "EXCEPTION":
            change = "RESOLVED"
        else:
            change = "CHECK_ADDED" if res_a == "NOT_CHECKED" else "CHECK_REMOVED"
        f = b or a
        assert f is not None
        rows.append({
            "rule_id": key[0], "field": key[1], "field_label": f.field_label,
            "baseline_result": res_a, "candidate_result": res_b,
            "baseline_rule_version": a.rule_version if a else None,
            "candidate_rule_version": b.rule_version if b else None,
            "expected_value": f.expected_value, "actual_value": f.actual_value,
            "candidate_reason": b.reason if b else None, "baseline_reason": a.reason if a else None,
            "change": change,
        })
    order = {"NEW_EXCEPTION": 0, "RESOLVED": 1, "CHECK_ADDED": 2, "CHECK_REMOVED": 3, "UNCHANGED": 4}
    return sorted(rows, key=lambda r: order[r["change"]])


def _summary(r: ValidationResult) -> dict[str, Any]:
    return {"overall": r.overall.value, "exception_count": r.exception_count, "match_count": r.match_count,
            "findings_digest": r.findings_digest,
            "exception_rules": sorted({f.rule_id for f in r.findings if f.result is FindingResult.EXCEPTION})}


def compare(request_data: Any, change_data: Any, baseline: LoadedConfig, candidate: LoadedConfig,
            scenario_id: str | None = None) -> dict[str, Any]:
    case: MaintenanceCase = build_case(request_data, change_data)
    ra = evaluate(case, baseline, scenario_id=scenario_id, run_id="REPLAY-BASELINE")
    rb = evaluate(case, candidate, scenario_id=scenario_id, run_id="REPLAY-CANDIDATE")
    rows = _finding_rows(ra, rb)
    return {
        "request_id": case.request.request_id,
        "change_id": case.change.change_id,
        "input_digest": case.input_digest,
        "baseline_result": _summary(ra),
        "candidate_result": _summary(rb),
        "outcome_changed": ra.overall != rb.overall,
        "changed_findings": sum(1 for r in rows if r["change"] != "UNCHANGED"),
        "findings": rows,
        "rule_diffs": _rule_diffs(baseline, candidate),
        "notice": "Replay only: deterministic engine, same inputs, two rule configurations. "
                  "No run is stored and nothing can be approved from this view.",
    }
