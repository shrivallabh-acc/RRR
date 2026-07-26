# RRR end-to-end demo -- runs all 5 golden fixtures and verifies verdicts match oracles.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1
#
# No Ollama required -- uses the default RuleBasedProvider (deterministic, no model).
# Each fixture uses a temporary config file pointing at its own inputs directory.
# Results are compared against the ideal.json oracle; a pass/fail table is printed.

param()
$ErrorActionPreference = "Continue"
$root   = Split-Path $PSScriptRoot -Parent
$golden = Join-Path $root "tests\golden"
$rrrcli = Join-Path $root ".venv\Scripts\rrr.exe"

function Invoke-RRR ([string]$Release, [string]$ConfigPath) {
    # Capture only stdout; stderr (INFO/DEBUG logs) flows to the console.
    $output = & $rrrcli --release $Release --config $ConfigPath
    return $output
}

# Fixture table: directory, release ir_name, expected verdict, expected score (0 = dont check).
$fixtures = @(
    ,@("g1_clean_release",  "Launch 36 - Unified Onboarding", "GO",          96)
    ,@("g2_failing_tests",  "Launch 37 - Payments Hub",       "NO_GO",       0)
    ,@("g3_borderline",     "Launch 38 - Advice Workbench",   "CONDITIONAL", 72)
    ,@("g4_missing_data",   "Launch 39 - Missing Data",       "INCOMPLETE",  0)
    ,@("g5_scope_creep",    "Launch 40 - Onboarding Plus",    "CONDITIONAL", 94)
)

$tmpDir = Join-Path $env:TEMP ("rrr_demo_" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

Write-Host ""
Write-Host "  RRR -- Release Readiness Results  |  End-to-End Demo"
Write-Host "  ======================================================"
Write-Host ""

$passed = 0
$failed = 0

foreach ($fix in $fixtures) {
    $fixDir     = $fix[0]
    $release    = $fix[1]
    $expVerdict = $fix[2]
    $expScore   = $fix[3]

    $inputsDir = Join-Path $golden ($fixDir + "\inputs")
    $brainDir  = (Join-Path $inputsDir "brain") -replace "\\", "/"
    $envFile   = (Join-Path $inputsDir "environment.json") -replace "\\", "/"
    $depFile   = (Join-Path $inputsDir "dependency.json")  -replace "\\", "/"
    $dbPath    = (Join-Path $tmpDir ($fixDir + ".sqlite")) -replace "\\", "/"

    $opsFile   = (Join-Path $inputsDir "operational.json") -replace "\\", "/"

    # Write a minimal YAML config override for this fixture.
    $lines = @(
        "sources:",
        "  brain:",
        "    dir: `"" + $brainDir + "`"",
        "    value_stream: `"Retirement-Services`"",
        "  environment:",
        "    type: file",
        "    path: `"" + $envFile + "`"",
        "  dependency:",
        "    type: file",
        "    path: `"" + $depFile + "`"",
        "  operational:",
        "    type: file",
        "    path: `"" + $opsFile + "`"",
        "memory:",
        "  sqlite_path: `"" + $dbPath + "`""
    )
    $configPath = Join-Path $tmpDir ($fixDir + ".yaml")
    Set-Content -Path $configPath -Value ($lines -join "`n") -Encoding UTF8

    # Run the CLI and capture stdout.
    $output = Invoke-RRR -Release $release -ConfigPath $configPath

    # Parse "VERDICT: GO  SCORE: 96  CONFIDENCE: 100%"
    $gotVerdict = "ERROR"
    $gotScore   = $null
    if ($output) {
        $vm = [regex]::Match($output, "VERDICT:\s+(\w+)")
        $sm = [regex]::Match($output, "SCORE:\s+(\d+)")
        if ($vm.Success) { $gotVerdict = $vm.Groups[1].Value }
        if ($sm.Success) { $gotScore   = [int]$sm.Groups[1].Value }
    }

    # Compare against oracle.
    $verdictOk = ($gotVerdict -eq $expVerdict)
    $scoreOk   = ($expScore -eq 0) -or ($gotScore -eq $expScore)
    $ok        = $verdictOk -and $scoreOk

    if ($ok) { $passed++ } else { $failed++ }

    $icon      = if ($ok) { "PASS" } else { "FAIL" }
    $scoreStr  = if ($gotScore -ne $null) { "$gotScore" } else { "n/a" }
    $expStr    = if ($expScore -ne 0) { ($expVerdict + "/" + $expScore) } else { $expVerdict }
    $prefix    = if ($ok) { "  [PASS]" } else { "  [FAIL]" }

    Write-Host ($prefix + "  " + $fixDir.PadRight(22) + "  " + $gotVerdict.PadRight(12) + "  score=" + $scoreStr + "  (expected " + $expStr + ")")
}

# Clean up temp files.
Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue

Write-Host ""
Write-Host ("  Results: " + $passed + " passed, " + $failed + " failed  out of " + $fixtures.Count + " fixtures")
Write-Host ""

if ($failed -gt 0) {
    Write-Host "  DEMO: FAIL -- one or more fixtures did not match the oracle."
    exit 1
} else {
    Write-Host "  DEMO: PASS -- all fixtures produced the expected verdict and score."
    exit 0
}
