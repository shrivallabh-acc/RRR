# Data Collection Guide — RRR

> How to populate the `data/<dimension>.json` files that gate-only assessors read
> before `rrr --release "<name>"` can produce a complete verdict.
>
> **Two ways to collect data (both write the same JSON files):**
> 1. **`rrr-collect` CLI (Phase 1, available now)** — interactive questionnaire driven
>    by each dimension's Pydantic schema; no JSON editing required.
> 2. **Tool adapters (Phase 2, planned)** — auto-populate fields from CI/CD tools
>    (Snyk, SonarQube, k6, axe, Grafana, etc.); see [Section 7](#7-building-a-tool-adapter).

---

## Contents

1. [Why data collection exists](#1-why-data-collection-exists)
2. [Architecture overview](#2-architecture-overview)
3. [The 14 supplementary dimensions](#3-the-14-supplementary-dimensions)
4. [rrr-collect CLI reference](#4-rrr-collect-cli-reference)
5. [rrr-ui Collect screen](#5-rrr-ui-collect-screen)
6. [CI/CD integration](#6-cicd-integration)
7. [Building a tool adapter](#7-building-a-tool-adapter)
8. [Per-dimension collection guide](#8-per-dimension-collection-guide)

---

## 1. Why data collection exists

RRR draws from two independent data sources:

| Source | Populated by | Covers |
|--------|-------------|--------|
| `brain/<value-stream>-history.json` | `rrr-ingest` (HTML → JSON) | Scope, Estimation, Test Readiness, Dependency (brain-backed) |
| `data/<dimension>.json` | `rrr-collect` CLI / `rrr-ui` Collect screen / tool adapters | All other dimensions — operability, observability, rollback, security, performance, accessibility, auditability, disaster recovery, data reconciliation, failure mode, dependency risk, production readiness, architecture fitness, architecture drift |

The brain pipeline handles RKT Program Metrics data automatically. The 14 supplementary
dimensions require data from your own toolchain — CI/CD pipelines, security scanners,
monitoring platforms, and manual sign-off checklists. `rrr-collect` is the bridge.

**Gate-only dimensions** (security, performance, accessibility, and all M6 additions) have
`weight = 0` in the scoring model: they never raise the weighted score but **can cap the
verdict downward** via the GateEngine (ADR-0013, ADR-0014). A CRITICAL risk factor in any
gate-only dimension forces a `NO_GO`; a MAJOR forces `CONDITIONAL`. Supplying complete,
accurate data is as important as a high weighted score.

---

## 2. Architecture overview

```
┌────────────────────────────────────────────────────────────────┐
│  Collection surfaces (ADR-0023)                                │
│  ─────────────────────────────                                 │
│  rrr-collect CLI              rrr-ui Collect screen            │
│  (InteractiveCollector)       (_DictCollector)                 │
│  [Phase 2: tool adapters]                                      │
└───────────────────────────┬────────────────────────────────────┘
                            │ calls
                            ▼
┌───────────────────────────────────────────────────────────────┐
│  CollectorRunner (shared business logic)                       │
│  ─────────────────────────────────────────────────────────   │
│  status()  — scan data/ for FRESH / STALE / MISSING per dim   │
│  run()     — collect() → validate(InputContract) → write JSON │
└───────────────────────────┬───────────────────────────────────┘
                            │ writes
                            ▼
                   data/<dimension>.json
                            │ read by
                            ▼
┌───────────────────────────────────────────────────────────────┐
│  Assessor (<Dim>SourceReader → <Dim>Assessor)                 │
│  score + risk factors → orchestrator → verdict                │
└───────────────────────────────────────────────────────────────┘
```

**Layer 1 — CollectorRunner** owns the write path: it validates the raw dict returned by
any collector against the dimension's `InputContract` (Pydantic v2), stamps `captured_at`,
and writes the JSON. Both CLI and UI call the same runner — no logic is duplicated.

**Layer 2 — BaseCollector** is the single extension point. Implement one `collect()` method
returning a raw dict; the runner handles validation and writing. `InteractiveCollector`
(Click prompts) and `_DictCollector` (UI form data) are both `BaseCollector` subclasses.

**Layer 3 — CollectorRegistry** maps dimension name strings to `InputContract` classes.
The CLI and UI query the registry rather than hard-coding dimension names.

**Data freshness:** Every written file contains a `captured_at` ISO 8601 timestamp.
`CollectorRunner.status()` compares this against a configurable `staleness_days` threshold
(default 7) and returns `FRESH`, `STALE`, or `MISSING` per dimension.

---

## 3. The 14 supplementary dimensions

Brain-backed dimensions (scope, estimation, test\_readiness, dependency) are excluded — they
are populated by `rrr-ingest` from the RKT HTML report and do not require manual collection.

### Always-on weighted dimensions

| Dimension | JSON file | InputContract | What it measures |
|-----------|-----------|---------------|-----------------|
| `operability` | `data/operability.json` | `OperabilityInput` | Deployment pipeline health, runbooks, on-call, change management |
| `observability` | `data/observability.json` | `ObservabilityInput` | Dashboards, SLO alerts, trace/log coverage |

### Gate-only dimensions (weight = 0, verdict-cap only)

These never add to the numeric score but can cap the verdict to `NO_GO` or `CONDITIONAL`.

| Dimension | JSON file | Gate trigger |
|-----------|-----------|-------------|
| `rollback` | `data/rollback.json` | CRITICAL: no plan; MAJOR: untested or partial |
| `security` | `data/security.json` | CRITICAL: SAST/DAST failed or critical CVEs > threshold; MAJOR: approvals missing |
| `performance` | `data/performance.json` | CRITICAL: load test failed or P99 > SLO; MAJOR: no capacity headroom |
| `accessibility` | `data/accessibility.json` | CRITICAL: critical WCAG violations > 0; MAJOR: major violations > 0 |
| `auditability` | `data/auditability.json` | CRITICAL: audit logging disabled or PII not logged |
| `disaster_recovery` | `data/disaster_recovery.json` | CRITICAL: no DR plan or RTO/RPO targets exceeded |
| `data_reconciliation` | `data/data_reconciliation.json` | CRITICAL: any reconciliation discrepancy; bypassed when `migration_applicable: false` |
| `failure_mode` | `data/failure_mode.json` | CRITICAL: failure modes undocumented or circuit breakers absent |
| `dependency_risk` | `data/dependency_risk.json` | CRITICAL: malicious packages or critical transitive CVEs > 0 |
| `production_readiness` | `data/production_readiness.json` | CRITICAL: capacity unconfirmed or checklist incomplete; MAJOR: any sign-off missing |
| `architecture_fitness` | `data/architecture_fitness.json` | CRITICAL: layering or banned-dependency violations |
| `architecture_drift` | `data/architecture_drift.json` | CRITICAL: banned technologies or ADR compliance < 80% |

### Tier filtering

| Tier | Excluded gate dimensions |
|------|--------------------------|
| `hotfix` | `accessibility`, `architecture_fitness`, `architecture_drift` |
| `standard` (default) | none |
| `major` | none |

### Field reference — auto-filled fields

All `InputContract` models share three fields that are never prompted — they are set by
`InteractiveCollector` and `CollectorRunner` automatically:

| Field | Value |
|-------|-------|
| `schema_version` | `"1.0.0"` |
| `release` | Value from `--release` flag or UI form |
| `captured_at` | ISO 8601 timestamp stamped by `CollectorRunner.run()` |

---

## 4. rrr-collect CLI reference

Install the package to get the `rrr-collect` entry point:

```powershell
pip install -e ".[dev]"
rrr-collect --help
```

### 4.1 Pre-flight status check

Before every assessment, check which files need refreshing:

```powershell
rrr-collect --status
```

Example output:
```
Data freshness status (tier: standard, data-dir: data)

  [FRESH ]  operability  0.2d old
  [STALE ]  observability  9.1d old
  [MISSING]  security
  [FRESH ]  rollback  1.4d old
  [MISSING]  performance
  ...

Run rrr-collect --release <name> --all to populate missing/stale files.
```

**Exit codes:**
- `0` — all active dimensions are FRESH
- `2` — one or more dimensions are STALE or MISSING (enables CI `if` gates)

Check for a specific tier (hotfix skips non-critical gate dimensions):

```powershell
rrr-collect --status --tier hotfix
```

Point at a non-default data directory:

```powershell
rrr-collect --status --data-dir path/to/data
```

### 4.2 Collect one dimension

```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension security
```

`InteractiveCollector` introspects `SecurityInput.model_fields` and presents one prompt per
non-auto field. Existing `data/security.json` values become defaults — press Enter to keep.

**Enum fields** show a choice menu:
```
  sast_status (passed/failed/not_run) [not_run]: passed
```

**Bool fields** use `y/N` confirm prompts:
```
  license_approved [N]: y
```

**Complex fields** (dict, list) cannot be prompted interactively — the CLI advises editing
the JSON file directly:
```
  [skip]  stakeholder_sign_offs: complex type — edit this field in the JSON file
```

Force overwrite even when the file is already FRESH:

```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension security --refresh
```

### 4.3 Collect all dimensions for a release

```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --all
```

Iterates every active dimension in registration order. FRESH files are skipped automatically.

Control the active dimension set with `--tier`:

```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --all --tier hotfix
```

Force overwrite of even fresh files:

```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --all --refresh
```

### 4.4 Speed up collection with --skip-optional

`Optional` fields that already have a value are kept silently rather than prompted:

```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --all --skip-optional
```

Useful in CI pipelines where optional fields were populated in a previous run and only
required fields need confirming.

### 4.5 Complete collection workflow

```powershell
# Step 1 — ingest fresh brain data from RKT HTML report
rrr-ingest --html-dir input --brain-dir brain --value-stream "OSM"

# Step 2 — check what supplementary data needs refreshing
rrr-collect --status --tier standard

# Step 3 — populate or update everything stale/missing
rrr-collect --release "OSM-2026-Q3-v1.4" --all --tier standard

# Step 4 — run the assessment (all data now fresh)
rrr --release "OSM-2026-Q3-v1.4" --tier standard
```

### 4.6 Flag reference

| Flag | Type | Default | Purpose |
|------|------|---------|---------|
| `--release`, `-r` | `str` | — | Release IR name. Required for `--dimension` and `--all` |
| `--tier` | choice | `standard` | `hotfix` / `standard` / `major` — controls active dimension set |
| `--dimension`, `-d` | `str` | — | Collect one named dimension interactively |
| `--all` | flag | off | Collect all active dimensions for the tier |
| `--status` | flag | off | Print freshness table and exit (no `--release` needed) |
| `--refresh` | flag | off | Overwrite FRESH files |
| `--skip-optional` | flag | off | Keep existing values for `Optional` fields without prompting |
| `--data-dir` | `str` | `data` | Directory for reading/writing `<dimension>.json` files |

---

## 5. rrr-ui Collect screen

Start the dashboard (requires `pip install rrr[ui]`):

```powershell
rrr-ui [--port 8080]
```

Navigate to **Collect** in the left sidebar (admin section, below **Ingest**).

### Status view (default)

Displays a badge-per-dimension table with Refresh button:

```
┌────────────────────────────────────────────────┐
│ Data Collection Status               [Refresh] │
│                                                │
│ operability          ● FRESH   0.2d old        │
│ observability        ● STALE   9.1d old        │
│ security             ○ MISSING                 │
│ rollback             ● FRESH   1.4d old        │
│ ...                                            │
└────────────────────────────────────────────────┘
```

Click any dimension row to switch to the form view for that dimension.

### Form view

Introspects the dimension's `InputContract` and renders type-appropriate NiceGUI widgets:

| Pydantic type | NiceGUI widget |
|---------------|---------------|
| `Enum` subclass | `ui.select` (dropdown of enum values) |
| `bool` | `ui.switch` |
| `int` / `float` | `ui.number` |
| `str` | `ui.input` |
| `dict` / `list` | Advisory note — edit the JSON file directly |

The **Release** field pre-populates from the existing JSON's `release` field when present
(update mode). Click **Save** to validate and write `data/<dimension>.json` via
`CollectorRunner.run()` — the same write path as the CLI.

---

## 6. CI/CD integration

### 6.1 GitHub Actions — release gate workflow

The following workflow collects dimension data from CI tool outputs, then gates the release
on the RRR verdict. Tool-specific data is written by inline Python scripts that parse each
tool's JSON output and map fields to the appropriate `InputContract`.

```yaml
# .github/workflows/release-gate.yml
name: Release Gate

on:
  workflow_dispatch:
    inputs:
      release_name:
        description: "Release IR name (e.g. OSM-2026-Q3-v1.4)"
        required: true
      tier:
        description: "Release risk tier"
        default: "standard"
        type: choice
        options: [hotfix, standard, major]

jobs:
  collect-data:
    name: Collect dimension data
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install RRR
        run: pip install -e ".[dev]"

      # ── Security (from SAST / CVE scan results) ────────────────────────────────
      - name: Write security.json
        run: |
          python - <<'EOF'
          import json, os
          # Parse your SAST tool's JSON output here.
          # This example reads env-var-injected results from the CI secrets.
          data = {
              "sast_status": os.environ.get("SAST_RESULT", "not_run"),
              "dast_status": "not_run",
              "open_critical_cves": int(os.environ.get("CRITICAL_CVES", "0")),
              "open_high_cves": int(os.environ.get("HIGH_CVES", "0")),
              "license_approved": os.environ.get("LICENSE_OK", "false").lower() == "true",
          }
          with open("data/security.json", "w") as f:
              json.dump(data, f, indent=2)
          EOF
        env:
          SAST_RESULT: "passed"
          CRITICAL_CVES: "0"
          HIGH_CVES: ${{ vars.HIGH_CVE_COUNT || '0' }}
          LICENSE_OK: "true"

      # ── Performance (from k6 summary export) ──────────────────────────────────
      - name: Write performance.json from k6 results
        # k6 writes a JSON summary when run with: k6 run --summary-export=k6-summary.json
        run: |
          python - <<'EOF'
          import json, os
          summary_path = os.environ.get("K6_SUMMARY", "")
          if summary_path:
              raw = json.loads(open(summary_path).read())
              metrics = raw.get("metrics", {})
              p99 = metrics.get("http_req_duration", {}).get("values", {}).get("p(99)")
              checks_fail = metrics.get("checks", {}).get("values", {}).get("fails", 0)
              status = "passed" if checks_fail == 0 else "failed"
          else:
              p99, status = None, "not_run"
          data = {
              "performance_test_status": status,
              "p99_latency_ms": float(p99) if p99 is not None else None,
              "slo_p99_threshold_ms": float(os.environ.get("SLO_P99_MS", "500")),
              "capacity_headroom_pct": float(os.environ.get("HEADROOM_PCT", "0")) or None,
          }
          with open("data/performance.json", "w") as f:
              json.dump(data, f, indent=2)
          EOF
        env:
          K6_SUMMARY: "k6-summary.json"   # set to "" if k6 did not run
          SLO_P99_MS: "500"
          HEADROOM_PCT: "42.0"

      # ── Remaining dimensions (interactive with --skip-optional) ───────────────
      - name: Collect remaining dimensions
        # --skip-optional keeps existing values for optional fields without prompting.
        # Dimensions already written above will still pass --status since they have
        # a fresh captured_at — rrr-collect skips FRESH files automatically.
        run: |
          rrr-collect \
            --release "${{ github.event.inputs.release_name }}" \
            --tier "${{ github.event.inputs.tier }}" \
            --all \
            --skip-optional

      - name: Upload dimension data as artifact
        uses: actions/upload-artifact@v4
        with:
          name: rrr-dimension-data
          path: data/*.json

  assess:
    name: Run RRR assessment
    needs: collect-data
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download dimension data
        uses: actions/download-artifact@v4
        with:
          name: rrr-dimension-data
          path: data/

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install RRR
        run: pip install -e ".[dev]"

      - name: Run assessment and save report
        run: |
          rrr --release "${{ github.event.inputs.release_name }}" \
              --tier "${{ github.event.inputs.tier }}" \
              --format markdown \
            | tee assessment-report.md
        # Non-zero exit does not fail the step — we gate explicitly below.
        continue-on-error: true

      - name: Gate on verdict
        run: |
          rrr --release "${{ github.event.inputs.release_name }}" \
              --tier "${{ github.event.inputs.tier }}"
          EXIT=$?
          # Exit 0=GO  1=NO_GO  2=CONDITIONAL  3=ERROR
          if [ $EXIT -eq 1 ]; then
            echo "::error::RRR verdict is NO_GO — release is blocked."
            exit 1
          fi

      - name: Upload assessment report
        uses: actions/upload-artifact@v4
        with:
          name: rrr-assessment-report
          path: assessment-report.md
```

### 6.2 Pre-flight freshness gate

Use the `--status` exit code to detect stale data before the assessment step and fail fast:

```yaml
- name: Pre-flight data freshness check
  run: rrr-collect --status --tier "${{ github.event.inputs.tier }}"
  # Exit 0 = all FRESH; exit 2 = stale/missing.
  # Use continue-on-error: true if you want the assessment to proceed anyway
  # and let rrr handle missing dimensions as INCOMPLETE.
```

### 6.3 Credential management

Tool adapters that call external APIs (see [Section 7](#7-building-a-tool-adapter)) read
credentials from environment variables only — never from config files. Inject them via
GitHub Actions secrets:

```yaml
env:
  SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
  SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
  SONARQUBE_HOST: ${{ secrets.SONARQUBE_HOST }}
```

Any adapter making an outbound network call must validate the target host against the
ADR-0010 allow-list before opening a connection. See [Section 7](#7-building-a-tool-adapter)
for the pattern.

---

## 7. Building a tool adapter

Phase 2 of the collection system replaces (or supplements) interactive prompts with
automated data from CI tools. An adapter is a `BaseCollector` subclass whose `collect()`
calls the tool's API or reads its output file, then returns a partial dict that the runner
validates against the dimension's `InputContract`.

### 7.1 Anatomy of an adapter

```python
# src/rrr/collectors/adapters/k6.py
"""k6 adapter — reads k6 JSON summary output and maps to PerformanceInput (ADR-0023)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rrr.collectors.base import BaseCollector, CollectorConfig


class K6Adapter(BaseCollector):
    """Reads a k6 summary-export JSON file and maps load-test results to PerformanceInput.

    k6 writes the summary when run with: k6 run --summary-export=<path>.
    File-based (no network call) — works in any CI environment without credentials.
    """

    def __init__(self, summary_path: Path | str) -> None:
        """Bind the adapter to a k6 JSON summary file.

        Args:
            summary_path: Path written by k6's --summary-export flag.
        """
        self._summary_path = Path(summary_path)

    @property
    def dimension(self) -> str:
        """Target dimension name."""
        return "performance"

    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Read the k6 summary and map metrics to PerformanceInput fields.

        Returns a partial dict — fields k6 does not provide are absent and
        fall back to their InputContract defaults after runner validation.

        Args:
            config: Runtime context (not used by file-based adapters).

        Returns:
            Dict with performance_test_status, p99_latency_ms.
        """
        raw = json.loads(self._summary_path.read_text(encoding="utf-8"))
        metrics = raw.get("metrics", {})

        p99 = (
            metrics.get("http_req_duration", {})
                   .get("values", {})
                   .get("p(99)")
        )
        # k6 sets checks.fails > 0 when any threshold is breached.
        checks_fail = (
            metrics.get("checks", {})
                   .get("values", {})
                   .get("fails", 0)
        )
        status = "passed" if checks_fail == 0 else "failed"

        result: dict[str, Any] = {"performance_test_status": status}
        if p99 is not None:
            result["p99_latency_ms"] = float(p99)
        return result
```

### 7.2 Using an adapter directly

Until adapters are registered in the CLI, wire them directly in a script or CI step:

```python
from pathlib import Path
from rrr.collectors.adapters.k6 import K6Adapter
from rrr.collectors.base import CollectorConfig
from rrr.collectors.registry import CollectorRegistry
from rrr.collectors.runner import CollectorRunner

registry = CollectorRegistry()
runner = CollectorRunner()
config = CollectorConfig(release="OSM-2026-Q3-v1.4", data_dir=Path("data"))

adapter = K6Adapter(summary_path="k6-summary.json")
result = runner.run(
    "performance",
    adapter,
    config,
    registry.model_for("performance"),
)
print(f"Written: {result.collected_at}")
```

### 7.3 Adapter conventions (ADR-0010, ADR-0023)

1. **Return a partial dict.** The runner validates the merged result against the
   `InputContract` — missing fields fall back to model defaults. Never raise an error for
   fields your tool cannot populate; let the model's default cover them.

2. **Network adapters must check the host allow-list.** Any adapter that makes an outbound
   HTTP call must validate the target host against `ConfigLoader`'s allow-list before
   connecting. `LocalLLMProvider` (`src/rrr/providers/local_llm.py`) is the reference
   implementation for this pattern.

3. **Read credentials from environment variables only.** Never embed tokens in source code
   or config files. Read with `os.environ.get("TOKEN_NAME")` and raise a clear error if
   missing.

4. **Tests must be offline.** Mock external calls (patch the HTTP client or file read).
   Place tests in `tests/unit/test_<adapter_name>_adapter.py` with at least 10 assertions
   covering: happy path, tool not available, credentials missing, malformed output.

### 7.4 Planned adapter roadmap

| Batch | Tool | Dimension(s) | API type | Status |
|-------|------|-------------|----------|--------|
| 1 | Snyk | `security`, `dependency_risk` | CLI subprocess (`snyk test --json`) | ⬜ planned |
| 1 | SonarQube | `security` | REST API (`/api/issues/search`) | ⬜ planned |
| 1 | k6 | `performance` | JSON summary file (offline) | ⬜ planned |
| 2 | axe / Lighthouse | `accessibility` | CLI subprocess + JSON report | ⬜ planned |
| 2 | Grafana | `observability` | REST API | ⬜ planned |
| 2 | Datadog | `observability`, `performance` | REST API | ⬜ planned |
| 2 | Terraform | `operability` | State file / CLI output | ⬜ planned |
| 2 | GitHub Actions | `operability` | REST API | ⬜ planned |
| 3 | OWASP Dependency-Check / Snyk SCA | `dependency_risk` | JSON report file | ⬜ planned |
| 3 | Gremlin | `failure_mode` | REST API | ⬜ planned |
| 3 | Dependency Cruiser / Import Linter | `architecture_fitness` | JSON report file | ⬜ planned |

---

## 8. Per-dimension collection guide

---

### Brain-backed dimensions — Scope / Estimation / Test Readiness / Dependency

**These four dimensions are populated automatically by `rrr-ingest`.**

1. Log into the RKT Program Metrics portal and navigate to your value stream.
2. Save the HTML programme report to the `input/` folder.
3. Run `rrr-ingest`:
   ```powershell
   rrr-ingest --html-dir input --brain-dir brain --value-stream "OSM"
   ```
4. Confirm your release appears:
   ```powershell
   rrr --list-releases --config configs/osm.yaml
   ```

Re-run `rrr-ingest` each time you download a fresh RKT report (at least once before the
final go/no-go assessment).

---

### Environment — brain-backed via `EnvironmentSourceReader`

Environment data (provisioning status, stability, component inventory) is sourced from
`data/environment.json` or a localhost API configured in `sources.environment`.
The `EnvironmentSourceReader` handles both paths; no `rrr-collect` dimension exists for
it because it is a weighted (non-gate-only) dimension fully covered by the brain/source
reader path.

---

### operability — `data/operability.json`

**What this covers:** Is the team operationally ready? Runbooks, on-call schedule,
deployment pipeline health, change-management approval.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension operability
```

**Key fields and where to get them:**

| Field | Where to find it |
|-------|-----------------|
| `deployment_pipeline` | CI/CD dashboard (GitHub Actions, Jenkins, Azure DevOps) |
| `change_freeze` | Change Advisory Board (CAB) calendar / release management |
| `recent_deployment_failures` | CI/CD deployment history for the last 30 days |
| `runbook_complete` | Ops runbook in Confluence/wiki — check it exists and is current |
| `runbook_last_tested_days_ago` | Last runbook walkthrough date in the ops log |
| `on_call_schedule_active` | PagerDuty / OpsGenie schedule for the release window |
| `escalation_paths_defined` | Incident response doc — named escalation contacts |
| `change_mgmt_approved` | CAB approval ticket / ServiceNow record |
| `operational_docs_reviewed` | Release checklist — ops documentation review item |

**Who provides this:** Release Manager (pipeline status) + Engineering Lead (runbook status).

**Phase 2 automation (planned):** GitHub Actions adapter → `deployment_pipeline` from the
latest workflow run status.

---

### observability — `data/observability.json`

**What this covers:** Are dashboards, SLO monitors, distributed traces, and structured
logs in place so the team can see what the system is doing post-release?

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension observability
```

**Key fields and where to get them:**

| Field | Where to find it |
|-------|-----------------|
| `dashboards_configured` / `dashboards_count` | Grafana / Datadog — count dashboards tagged for this service |
| `slo_defined` | SLO configuration in your monitoring tool |
| `slo_alerts_configured` | Alert rules linked to SLO burn-down policies |
| `alert_coverage_pct` | % of service endpoints with an alert rule (rough estimate) |
| `trace_coverage_pct` | % of critical paths instrumented in Jaeger / Zipkin / X-Ray |
| `log_coverage_pct` | % of services emitting structured JSON logs |
| `runbooks_linked_to_alerts_pct` | % of alert rules with a `runbook_url` annotation |
| `monitoring_tool` | Primary tool name: `"grafana"`, `"datadog"`, `"newrelic"`, etc. |

**Who provides this:** Platform / SRE team.

**Phase 2 automation (planned):** Grafana adapter → dashboard count + alert coverage.
Datadog adapter → SLO status + trace coverage.

---

### rollback — `data/rollback.json`

**What this covers:** Is there a documented, tested rollback procedure? Can the team
revert this release within an acceptable time window?

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension rollback
```

**Key fields and where to get them:**

| Field | Where to find it |
|-------|-----------------|
| `rollback_plan` | Release runbook / deployment wiki — `documented` / `partial` / `none` |
| `rollback_tested` | Was the procedure run end-to-end in staging? |
| `rollback_test_date` | Date of the staging rehearsal (YYYY-MM-DD) |
| `estimated_rollback_minutes` | Time the staging rehearsal; ask the DevOps lead if untested |
| `automated_rollback_available` | Does the platform support one-click rollback (K8s, ArgoCD, Spinnaker)? |
| `data_rollback_applicable` | True only if this release includes a data migration |
| `data_rollback_plan_exists` | Set to true only when a data-migration undo script exists and is reviewed |

**Who provides this:** Release Manager + DevOps / Platform team.

---

### security — `data/security.json`

**What this covers:** SAST / DAST scan outcomes, open CVEs, licence review, and
data-privacy sign-off. SAST/DAST failures and critical CVEs are hard NO-GO triggers.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension security
```

**Key fields and how to populate them:**

| Field | Tool / Process |
|-------|---------------|
| `sast_status` | SonarQube / Semgrep / Checkmarx scan result: `passed` / `failed` / `not_run` |
| `dast_status` | OWASP ZAP / Burp Suite scan against staging: `passed` / `failed` / `not_run` |
| `open_critical_cves` | `snyk test --json` or `trivy image` → count CRITICAL CVEs |
| `open_high_cves` | Same scan → count HIGH CVEs |
| `license_approved` | Confirm with Security/Compliance team that licence review is complete |
| `data_privacy_approved` | Confirm Privacy/Legal team signed off GDPR impact assessment |
| `pen_test_passed` | External pen test result: `true` / `false` / `null` (not yet run) |

**Phase 2 automation (planned):**
- SonarQube adapter → `sast_status` from latest analysis
- Snyk adapter → `open_critical_cves`, `open_high_cves` from `snyk test --json`

---

### performance — `data/performance.json`

**What this covers:** Did the release pass a load test? Is P99 latency within the SLO?
Is there sufficient capacity headroom?

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension performance
```

**Key fields and how to populate them:**

| Field | Tool / Process |
|-------|---------------|
| `performance_test_status` | k6 / Gatling / JMeter run result: `passed` / `failed` / `not_run` |
| `p99_latency_ms` | P99 response time from the load test report in milliseconds |
| `slo_p99_threshold_ms` | Your SLO target for P99 in ms (e.g., 500.0 for 500 ms) |
| `capacity_headroom_pct` | 100 − peak\_load\_pct from your APM or capacity planning tool |

**Run k6 and capture the summary export:**
```powershell
k6 run load-test.js --summary-export=k6-summary.json
```

The `p99` value is at `metrics.http_req_duration.values["p(99)"]` in the JSON output.

**Phase 2 automation (planned):** k6 adapter reads the summary file and maps fields
automatically; Datadog adapter pulls SLO/APM data.

---

### accessibility — `data/accessibility.json`

**What this covers:** WCAG compliance — critical violations (barriers preventing access)
are a hard NO-GO for public-facing or regulated applications.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension accessibility
```

**Automated scan using axe-core CLI:**
```powershell
npm install -g @axe-core/cli
axe https://staging.example.com --save axe-results.json
```

Map axe results to fields:
- `critical` impact → `critical_violations`
- `serious` impact → `major_violations`
- `moderate` / `minor` → `minor_violations`

**Lighthouse alternative:**
```powershell
lighthouse https://staging.example.com --output json --output-path lighthouse.json
```

For complex flows, supplement with a manual review by a QA engineer using NVDA + Firefox
or VoiceOver + Safari; record in `manual_review_complete` and `manual_review_passed`.

**Phase 2 automation (planned):** axe adapter → parse `axe-results.json` and map violation
counts; Lighthouse adapter → map accessibility score and issue categories.

---

### auditability — `data/auditability.json`

**What this covers:** Are regulated business events logged to an immutable, compliant
audit trail? Required for financial, healthcare, and GDPR-regulated releases.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension auditability
```

**Key fields and how to populate them:**

| Field | How to determine |
|-------|-----------------|
| `audit_logging_enabled` | Check app config / feature flags for your audit logging framework |
| `regulated_events_logged` | Confirm every event mandated by your regulation is captured (SOX, FCA, GDPR) |
| `audit_log_immutability_guaranteed` | Log writes to WORM/append-only storage (CloudTrail, Splunk, immutable S3)? |
| `data_retention_days` | Confirm configured retention policy; typically ≥ 365 days for financial |
| `gdpr_logging_compliant` | Confirm log avoids excess PII storage; reviewed by Privacy team? |
| `pii_access_logged` | Every PII read/write captured with user identity and timestamp? |
| `audit_trail_tested` | Trigger a regulated event in staging; verify it appears in the audit log |

**Who provides this:** Security / Compliance team with input from Engineering.

---

### disaster\_recovery — `data/disaster_recovery.json`

**What this covers:** Has a DR test been run? Are RTO and RPO targets met? Typically
tested quarterly; result remains valid until the next test or a significant architecture change.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension disaster_recovery
```

**Key fields and how to populate them:**

| Field | How to determine |
|-------|-----------------|
| `dr_plan_exists` | Documented DR plan approved and stored in Confluence/wiki? |
| `dr_last_tested_date` | Date of last DR rehearsal (YYYY-MM-DD) from SRE records |
| `rto_target_minutes` | Agreed RTO from your SLA / DR policy document |
| `rto_tested_minutes` | Actual recovery time from the last DR test report |
| `rpo_target_minutes` | Agreed RPO from your SLA / DR policy document |
| `rpo_tested_minutes` | Actual data-loss window from the last DR test report |
| `failover_tested` | Was traffic actually switched (not just a paper exercise)? |
| `data_backup_verified` | Backup integrity and restorability validated in the last backup drill? |
| `dr_test_max_age_days` | Default 180 (6 months); adjust if your policy requires more frequent tests |

**Who provides this:** Infrastructure / SRE team.

If `dr_last_tested_date` is older than `dr_test_max_age_days`, the assessor raises a MAJOR
risk. Request a DR re-test or obtain a risk waiver.

---

### data\_reconciliation — `data/data_reconciliation.json`

> **Opt-in only.** Set `migration_applicable: false` (or omit the file entirely) for
> releases with no data migration — all reconciliation checks are bypassed.

**What this covers:** Did data survive the migration intact? Any discrepancy between
source and target record counts is a hard CRITICAL trigger.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension data_reconciliation
```

**Steps for a migration release:**

1. Capture the pre-migration count from the source system:
   ```sql
   SELECT COUNT(*) FROM <table> WHERE <filter>;  -- → pre_migration_record_count
   ```

2. Run the migration in a staging/shadow environment.

3. Capture the post-migration count from the target:
   ```sql
   SELECT COUNT(*) FROM <migrated_table> WHERE <filter>;  -- → post_migration_record_count
   ```

4. Run your reconciliation script (checksum or business-key comparison); record
   `discrepancy_count` and `discrepancy_pct`. Any non-zero discrepancy is CRITICAL.

5. Get sign-off from the Data Engineering lead: `reconciliation_approved: true`.

**Who provides this:** Data Engineering team. The reconciliation script can write the JSON directly as a CI artifact.

---

### failure\_mode — `data/failure_mode.json`

**What this covers:** Have failure modes been documented and tested? Circuit breakers,
timeouts, graceful degradation, and chaos test outcomes.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension failure_mode
```

**Key fields and how to populate them:**

| Field | How to determine |
|-------|-----------------|
| `failure_modes_documented` | Design doc / FMEA register covers every critical path failure mode? |
| `critical_paths_covered_pct` | % of critical user journeys with a failure mode analysis |
| `circuit_breakers_configured` | Circuit breakers (Hystrix, Resilience4j, custom) on all external calls? |
| `timeout_policies_defined` | Every outbound call has an explicit timeout and retry policy? |
| `chaos_tests_run` | Chaos / fault-injection tests run for this release? |
| `chaos_pass_rate_pct` | % of chaos experiments the system survived within acceptable bounds |
| `chaos_test_date` | ISO 8601 date of the most recent chaos test run |
| `graceful_degradation_tested` | System returns degraded response (not error) when a dependency fails? |
| `fmea_complete` | FMEA document completed and reviewed? |

**Phase 2 automation (planned):** Gremlin adapter → attack results → `chaos_pass_rate_pct`.

---

### dependency\_risk — `data/dependency_risk.json`

> **Distinct from the Dependency assessor.** The Dependency assessor tracks internal
> programme delivery completion (is Team B's API ready?). Dependency Risk tracks
> software supply-chain integrity — EOL packages, malicious libraries, transitive CVEs.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension dependency_risk
```

**Run a Software Composition Analysis (SCA) scan:**
```powershell
# Snyk
snyk test --json > snyk-sca-results.json

# OWASP Dependency-Check
dependency-check --project "<name>" --scan . --format JSON --out dep-check/

# pip-audit (Python)
pip-audit --format json -o pip-audit-results.json
```

**Key fields and how to populate them:**

| Field | How to determine |
|-------|-----------------|
| `sca_tool` | Name of the tool used: `"snyk"`, `"dependabot"`, `"owasp-dep-check"` |
| `sca_scan_date` | Date of the most recent SCA scan (ISO 8601) |
| `eol_dependencies_count` | Direct dependencies past end-of-life from SCA report |
| `critical_transitive_cves` | CVSS ≥ 9.0 CVEs in transitive (indirect) deps from SCA report |
| `high_transitive_cves` | CVSS 7.0–8.9 CVEs in transitive deps |
| `known_malicious_packages` | Packages flagged malicious / typosquatted — **any non-zero is CRITICAL** |
| `supply_chain_violations` | Policy violations: unapproved sources, licence conflicts, unsigned packages |
| `pinned_dependencies_pct` | % of direct deps with an exact pinned version (`==`, `~=` in Python; exact in lock file) |

**Phase 2 automation (planned):** Snyk SCA adapter parses `snyk test --json` output and
maps fields automatically; OWASP Dependency-Check adapter reads the JSON report.

---

### production\_readiness — `data/production_readiness.json`

**What this covers:** Is everything in place for a safe go-live? Capacity confirmed,
feature flags set, go-live checklist complete, all stakeholders signed off.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension production_readiness
```

> **Note:** `stakeholder_sign_offs` is a `dict[str, bool | None]` field. It cannot be
> populated via the interactive CLI — edit `data/production_readiness.json` directly
> after running the CLI.

Expected sign-off structure:
```json
"stakeholder_sign_offs": {
  "product": true,
  "engineering": true,
  "security": true,
  "operations": null
}
```
`true` = signed, `false` = declined, `null` = pending.

**Key fields and how to populate them:**

| Field | How to determine |
|-------|-----------------|
| `capacity_confirmed` | Infrastructure team confirms environment is sized for peak post-release load |
| `feature_flags_configured` | Feature flag service (LaunchDarkly, Flagsmith) — flags set for release target |
| `go_live_checklist_complete` | Release checklist in Jira / Confluence — all items ticked |
| `stakeholder_sign_offs` | Written confirmation from product, engineering, security, operations leads |
| `release_comms_prepared` | Customer notices, internal announcements, and changelog entries ready |
| `support_team_briefed` | Support/CS briefed on new features, known issues, and escalation path |
| `rollback_decision_criteria_defined` | Explicit error-rate / SLO / incident thresholds that trigger rollback |
| `post_release_monitoring_plan` | Named on-call person, dashboards to watch, minimum monitoring window |

**Who provides this:** Release Manager (aggregates across all teams).

---

### architecture\_fitness — `data/architecture_fitness.json`

**What this covers:** Do automated architecture tests pass? Coupling violations, layer
bypasses, and banned-dependency use are CRITICAL triggers.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension architecture_fitness
```

**Recommended: automate in CI**

```powershell
# Python — import-linter
lint-imports --config .importlinter

# Any codebase — Dependency Cruiser (outputs JSON)
npx depcruise src --output-type json --output-to dep-cruise-results.json
```

Map the JSON output to fields:
- `layering_violations` — calls that skip a layer (UI → repository bypassing service)
- `coupling_violations` — unwanted cross-component or cross-context dependencies
- `banned_dependency_violations` — references to explicitly banned packages
- `violations` — list of human-readable violation descriptions for LLM narration

**Phase 2 automation (planned):** Dependency Cruiser adapter reads the JSON report;
Import Linter adapter parses its output.

---

### architecture\_drift — `data/architecture_drift.json`

**What this covers:** How far has the codebase drifted from the approved architecture
baseline? Banned technologies and ADR compliance < 80% are CRITICAL triggers.

**Collect interactively:**
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension architecture_drift
```

**Key fields and how to populate them:**

| Field | How to determine |
|-------|-----------------|
| `baseline_version` | Architecture baseline version — ADR collection commit hash or doc version |
| `adr_compliance_pct` | % of applicable ADRs reflected in the current codebase (manual review or automated check) |
| `banned_technologies_detected` | Scan codebase for technologies on your Approved Technology List banned list |
| `unapproved_patterns` | Design patterns used that were never approved via ADR or tech standard |
| `tech_standard_violations` | Deviations from technology standards (deprecated runtimes, non-standard logging) |
| `drift_score` | 0–1 score from your drift assessment tool; 0 = no drift, 1 = full divergence |
| `approved_deviations` | Count of known, ADR-approved deviations (subtracted from raw violation count) |

**Who provides this:** Architecture team with Engineering support.

---

## JSON file format reference

Every `data/<dimension>.json` follows the same envelope:

```json
{
  "schema_version": "1.0.0",
  "release": "OSM-2026-Q3-v1.4",
  "captured_at": "2026-07-16T09:30:00.000Z",
  "<dimension-specific fields>": "..."
}
```

- `schema_version` — always `"1.0.0"` for the current model generation.
- `release` — the IR name from `--release` or the UI form.
- `captured_at` — ISO 8601 with millisecond precision, UTC, stamped by `CollectorRunner.run()`.
- Unknown fields are silently ignored (`InputContract` uses `extra=ignore`).
- Missing required fields cause a `pydantic.ValidationError` — the runner reports the error
  and does not write the file.

**Example — clean security posture:**
```json
{
  "schema_version": "1.0.0",
  "release": "OSM-2026-Q3-v1.4",
  "captured_at": "2026-07-16T09:30:00.000Z",
  "sast_status": "passed",
  "dast_status": "passed",
  "open_critical_cves": 0,
  "open_high_cves": 2,
  "license_approved": true,
  "data_privacy_approved": true,
  "pen_test_passed": null
}
```

**Example — data migration release with reconciliation:**
```json
{
  "schema_version": "1.0.0",
  "release": "OSM-2026-Q3-v1.4",
  "captured_at": "2026-07-16T09:30:00.000Z",
  "migration_applicable": true,
  "pre_migration_record_count": 1247890,
  "post_migration_record_count": 1247890,
  "reconciliation_run": true,
  "reconciliation_date": "2026-07-15",
  "discrepancy_count": 0,
  "discrepancy_pct": 0.0,
  "reconciliation_approved": true
}
```

---

## Freshness guidelines

| Dimension | Recollect when | Maximum age |
|-----------|---------------|-------------|
| Brain data | Fresh RKT export available | 7 days |
| `operability` | Pipeline status or runbook change | 7 days |
| `observability` | Dashboard / alert rule change | 14 days |
| `rollback` | Rollback plan change | 14 days |
| `security` | New build or dependency update | 3 days |
| `performance` | New build or config change | 7 days |
| `accessibility` | Any UI change | 7 days |
| `auditability` | Logging config change | 30 days |
| `disaster_recovery` | Architecture change | 90 days |
| `data_reconciliation` | Migration dry-run update | 1 day (release day) |
| `failure_mode` | Service topology change | 30 days |
| `dependency_risk` | New build | 3 days |
| `production_readiness` | Any sign-off expires | 1 day (release day) |
| `architecture_fitness` | Any code change | 1 day (CI: every build) |
| `architecture_drift` | Significant code change | 30 days |

---

## Troubleshooting

**`rrr` says a dimension is UNAVAILABLE**

The source file is missing or the source is not configured. Check freshness:
```powershell
rrr-collect --status
```

**A dimension shows STALE**

The `captured_at` timestamp is outside the freshness window (7 days by default).
Re-collect:
```powershell
rrr-collect --release "OSM-2026-Q3-v1.4" --dimension <dim> --refresh
```

**A gate-only dimension caps the verdict but I don't know which risk factor triggered it**

Run with `--verbose` to see all risk factors in the JSON output:
```powershell
rrr --release "OSM-2026-Q3-v1.4" --tier standard --verbose
```
The `risk_factors` array in the JSON output lists every CRITICAL and MAJOR risk factor
with its source dimension and triggering field.

**I want to exclude a gate dimension for a specific release type**

Configure `excluded_gate_dims` on the tier in `default_config.yaml` or your release config:
```yaml
tiers:
  hotfix:
    excluded_gate_dims: [accessibility, architecture_fitness, architecture_drift]
```
Document the exclusion rationale in an ADR or exception record.
