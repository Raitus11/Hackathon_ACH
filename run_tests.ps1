# Runs all tests and regenerates reports\scenario_results.md (+ .json). Usage: .\run_tests.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = if (Test-Path .venv\Scripts\python.exe) { (Resolve-Path .venv\Scripts\python.exe).Path } else { "python" }
New-Item -ItemType Directory -Force reports | Out-Null
Push-Location backend
& $py -m pytest -p no:warnings --junitxml=..\reports\pytest_junit.xml
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { exit $code }
& $py scripts\run_scenarios.py
exit $LASTEXITCODE
