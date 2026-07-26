# Full quality gate — run all four checks in order.
# Usage: .\.venv\Scripts\pwsh.exe scripts\check_all.ps1
# Exit 0 = all pass; non-zero = at least one failed.
#
# Gate order (same as pre-commit hooks + CI):
#   1. Comment coverage  (scripts/check_comments.py)
#   2. Ruff lint         (ruff check src tests)
#   3. Ruff format check (ruff format --check src tests)
#   4. Mypy strict       (mypy src)
#   5. Pytest (HYPOTHESIS_PROFILE=full — 200 examples; use 'ci' during active development)
#
# Fast development loop (do NOT use this script):
#   pytest -m "unit or golden" -x -q               # ~8 seconds, every commit
#   pytest -m "unit" -x -q                          # ~3 seconds, every save
#   pytest -n auto                                  # parallel full suite (requires pytest-xdist)

$ErrorActionPreference = "Continue"
$allPassed = $true

function Invoke-Step {
    param([string]$Label, [scriptblock]$Cmd)
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    & $Cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $Label" -ForegroundColor Red
        $script:allPassed = $false
    } else {
        Write-Host "PASS: $Label" -ForegroundColor Green
    }
}

Invoke-Step "Comments" { .venv\Scripts\python.exe scripts\check_comments.py src\rrr }
Invoke-Step "Ruff lint" { .venv\Scripts\python.exe -m ruff check src tests }
Invoke-Step "Ruff format" { .venv\Scripts\python.exe -m ruff format --check src tests }
Invoke-Step "Mypy" { .venv\Scripts\python.exe -m mypy src }
Invoke-Step "Pytest (full Hypothesis)" {
    $env:HYPOTHESIS_PROFILE = "full"
    .venv\Scripts\python.exe -m pytest
    Remove-Item Env:\HYPOTHESIS_PROFILE -ErrorAction SilentlyContinue
}

Write-Host ""
if ($allPassed) {
    Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "ONE OR MORE CHECKS FAILED" -ForegroundColor Red
    exit 1
}
