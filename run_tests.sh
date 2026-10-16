#!/usr/bin/env bash
# Runs all tests and regenerates reports/scenario_results.md (+ .json). Usage: ./run_tests.sh
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PY="$(command -v python3 || command -v python)"
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
[[ -x "$ROOT/.venv/Scripts/python.exe" ]] && PY="$ROOT/.venv/Scripts/python.exe"
mkdir -p reports
(cd backend && "$PY" -m pytest -p no:warnings --junitxml="$ROOT/reports/pytest_junit.xml")
"$PY" scripts/run_scenarios.py
