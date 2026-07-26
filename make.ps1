# make.ps1 — PowerShell quality gate for RRR (no GNU Make required)
# Usage: .\make.ps1 [lint|type|test|fix|check|all]
# All commands use the project .venv; no activation needed.

param([string]$Target = "check")

$Python = ".venv\Scripts\python.exe"
$Ruff   = ".venv\Scripts\ruff.exe"

function Invoke-Lint {
    & $Ruff check src tests; if (-not $?) { exit 1 }
    & $Ruff format --check src tests; if (-not $?) { exit 1 }
}

function Invoke-Type {
    & $Python -m mypy src; if (-not $?) { exit 1 }
}

function Invoke-Test {
    & $Python -m pytest; if (-not $?) { exit 1 }
}

function Invoke-Fix {
    & $Ruff format src tests
    & $Ruff check --fix src tests
}

switch ($Target) {
    "lint"  { Invoke-Lint }
    "type"  { Invoke-Type }
    "test"  { Invoke-Test }
    "fix"   { Invoke-Fix }
    "check" { Invoke-Lint; Invoke-Type; Invoke-Test }
    "all"   { Invoke-Lint; Invoke-Type; Invoke-Test }
    default { Write-Error "Unknown target: $Target. Use: lint, type, test, fix, check, all"; exit 1 }
}
