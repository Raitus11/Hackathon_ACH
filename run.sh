#!/usr/bin/env bash
# One-command start (macOS/Linux/Git Bash). Usage: ./run.sh [--build-ui] [--port 8000]
# Uses the prebuilt UI in frontend/dist; --build-ui rebuilds it (needs Node 18+).
set -euo pipefail
cd "$(dirname "$0")"
PORT=8000; BUILD_UI=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-ui) BUILD_UI=1 ;;
    --port) PORT="$2"; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac; shift
done
PY="${PYTHON:-python3}"
if [[ ! -d .venv ]]; then "$PY" -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
python -m pip install -q --disable-pip-version-check -r backend/requirements.txt
if [[ $BUILD_UI -eq 1 || ! -f frontend/dist/index.html ]]; then
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi
echo ""
echo "  ACH Validation Workbench (SYNTHETIC DATA · SIMULATED SYSTEMS)"
echo "  Open http://localhost:${PORT}"
echo ""
exec python -m uvicorn app.api:app --app-dir backend --host 127.0.0.1 --port "$PORT"
