# One-command start (Windows PowerShell). Usage: .\run.ps1 [-BuildUi] [-Port 8000]
# Uses the prebuilt UI in frontend\dist; -BuildUi rebuilds it (needs Node 18+).
param([switch]$BuildUi, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { py -3 -m venv .venv; if ($LASTEXITCODE -ne 0) { python -m venv .venv } }
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install -q --disable-pip-version-check -r backend\requirements.txt
if ($BuildUi -or -not (Test-Path frontend\dist\index.html)) {
  Push-Location frontend; npm install --no-audit --no-fund; npm run build; Pop-Location
}
Write-Host ""
Write-Host "  ACH Validation Workbench (SYNTHETIC DATA - SIMULATED SYSTEMS)"
Write-Host "  Open http://localhost:$Port"
Write-Host ""
& $py -m uvicorn app.api:app --app-dir backend --host 127.0.0.1 --port $Port
