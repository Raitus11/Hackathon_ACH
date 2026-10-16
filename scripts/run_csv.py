"""Validate a CSV input set (the team's 4-file export) from the command line.

Same adapter and rule engine as the UI and POST /api/csv/batches; nothing is stored.
Prints one line per request and every exception. Exit code 1 if any request has an exception
or could not be ingested.

Usage:
  python scripts/run_csv.py                                   # bundled sample: data/csv_input_set
  python scripts/run_csv.py "C:\\Users\\...\\export"          # the real export folder
  python scripts/run_csv.py <folder> --rules config/rules/samples/ach_db_next_day.v1.1.0.yaml --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.config import ConfigError, load_ruleset  # noqa: E402
from app.csv_ingest import FILE_KEYS, build_batch, load_mapping  # noqa: E402
from app.engine import evaluate  # noqa: E402
from app.explain import show  # noqa: E402
from app.ingest import IngestError, build_case  # noqa: E402
from app.models import FindingResult  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", default=str(REPO / "data" / "csv_input_set"))
    ap.add_argument("--rules", default=str(REPO / "config" / "rules" / "ach_db_next_day.yaml"))
    ap.add_argument("--mapping", default=str(REPO / "config" / "csv_mapping.yaml"))
    ap.add_argument("--json", help="also write the full results to this file")
    a = ap.parse_args()

    folder = Path(a.folder)
    files = [(p.name, p.read_bytes()) for p in sorted(folder.glob("*.csv"))]
    try:
        cfg = load_ruleset(Path(a.rules))
        batch = build_batch(files, load_mapping(Path(a.mapping)))
    except (ConfigError, IngestError) as exc:
        print(f"ERROR {getattr(exc, 'code', 'CONFIG_INVALID')}: {exc.message}", file=sys.stderr)
        for d in exc.details:
            print(f"  - {d}", file=sys.stderr)
        print(f"Expected files in {folder}: {', '.join(k + '.csv' for k in FILE_KEYS)}", file=sys.stderr)
        return 2

    print(f"Rules {cfg.path.name} v{cfg.ruleset.ruleset.version} ({cfg.short_hash}) - {len(batch.cases)} request(s)\n")
    report, failed = [], 0
    for case in batch.cases:
        try:
            result = evaluate(build_case(case.request, case.implemented_change), cfg)
        except IngestError as exc:
            failed += 1
            print(f"{case.request_id:<12} REJECTED   {exc.code}: {exc.message}")
            for d in exc.details:
                print(f"    {d.get('location')}: {d.get('message')}")
            report.append({"request_id": case.request_id, "error": {"code": exc.code, "details": exc.details}})
            continue
        exc_findings = [f for f in result.findings if f.result is FindingResult.EXCEPTION]
        failed += bool(exc_findings)
        label = f"  [{case.scenario_key}]" if case.scenario_key else ""
        print(f"{case.request_id:<12} {result.overall.value:<10} {len(exc_findings)} exception(s){label}")
        for f in exc_findings:
            print(f"    {f.rule_id} {f.exception_type.value} - {f.field_label}: "
                  f"expected {show(f.expected_value)} actual {show(f.actual_value)}")
            print(f"      {f.reason}")
        report.append({"request_id": case.request_id, "result": result.model_dump(mode="json")})

    for w in batch.warnings:
        print(f"\nWARNING {w}", file=sys.stderr)
    if a.json:
        Path(a.json).write_text(json.dumps({"files": batch.files, "warnings": batch.warnings, "requests": report},
                                           indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
