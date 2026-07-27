# Release Readiness Results (RRR)

An **AI-first, local-first** Python CLI that turns programme release metrics into an
auditable **GO / NO-GO / CONDITIONAL / INCOMPLETE** verdict — with a deterministic
numeric score, an LLM-written rationale, and a full audit trail.

RRR ingests release snapshots from the **RKT Program Metrics** HTML reports, enriches
them with environment, dependency, and operational data you supply, fans out up to 21
parallel assessors, then fuses the results into a single weighted verdict backed by
traceable evidence. Every run is persisted to a local SQLite database so trend lines and
release-over-release comparisons are always available.

---

## Contents

- [What RRR does](#what-rrr-does)
- [How it works](#how-it-works)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The four CLI tools](#the-four-cli-tools)
  - [rrr — assess a release](#rrr--assess-a-release)
  - [rrr-ingest — convert RKT HTML reports](#rrr-ingest--convert-rkt-html-reports)
  - [rrr-collect — collect dimension data interactively](#rrr-collect--collect-dimension-data-interactively)
  - [rrr-ui — web dashboard](#rrr-ui--web-dashboard)
- [Configuration reference](#configuration-reference)
- [Data sources](#data-sources)
  - [Brain data (RKT snapshots)](#brain-data-rkt-snapshots)
  - [Dimension data files](#dimension-data-files)
- [Assessors](#assessors)
  - [Core scored dimensions](#core-scored-dimensions)
  - [Gate-only dimensions](#gate-only-dimensions)
- [LLM providers](#llm-providers)
- [Output formats](#output-formats)
- [Release risk tiers](#release-risk-tiers)
- [Scoring and verdict logic](#scoring-and-verdict-logic)
- [Historical trends](#historical-trends)
- [Web dashboard](#web-dashboard)
- [Development](#development)
- [Project structure](#project-structure)
- [Status](#status)

---

## What RRR does

Release managers in large programmes (dozens of parallel releases, multiple value
streams) face the same question before every release window: **is this safe to ship?**
Answering it manually means aggregating data from multiple dashboards, chasing status
updates, and applying subjective judgment under time pressure.

RRR replaces that with a **reproducible, auditable assessment pipeline**:

1. Pulls test results, scope metrics, estimation health, environment state, dependency
   status, and operational readiness from structured data sources.
2. Scores each dimension independently (deterministic math — no LLM involvement in the
   numbers).
3. Fuses dimensions into a weighted overall score.
4. Applies veto/cap gates: a CRITICAL risk factor always caps the verdict to NO_GO
   regardless of the score.
5. Asks an LLM to write the rationale, risk narrative, and remediation plan — but the
   **verdict label and score are never influenced by the LLM**.
6. Persists the result to SQLite and surfaces trends vs the previous run.

**The output answers:** GO / NO_GO / CONDITIONAL / INCOMPLETE, with a 0–100 score,
a confidence percentage, and a list of the specific risk factors that drove the result.

---

## How it works

```
                    ┌─────────────────────────────────┐
                    │          ConfigLoader           │
                    │  default_config.yaml + overrides│
                    └──────────────┬──────────────────┘
                                   │
               ┌───────────────────▼──────────────────────┐
               │               Orchestrator               │
               │   fan-out (ThreadPoolExecutor)            │
               └───┬──────┬──────┬──────┬──────┬──────────┘
                   │      │      │      │      │
               Scope  Estim. Environ. TestR. Depend.  ... (up to 21 assessors)
                   │      │      │      │      │
               [DimensionResult × N — deterministic score + risk factors]
                   │      │      │      │      │
               └───┴──────┴──────┴──────┴──────┘
                                   │
                        Weighted score + gate engine
                                   │
                        LLMProvider.reason()  ← rationale only
                                   │
                        AssessmentOutputModel
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
              SQLite + Chroma             CLI / rrr-ui
              (persist + trends)         (text / JSON / HTML)
```

**Key architectural invariant:** The numeric score, verdict label, and gate decisions are
always computed by deterministic code. The LLM only writes prose — it cannot change the
verdict.

---

## Installation

**Requirements:** Python 3.11+ (developed on 3.14). Windows, macOS, Linux.

```powershell
# Core install — no model required (uses RuleBasedProvider by default)
pip install -e "."

# With the developer toolchain
pip install -e ".[dev]"

# Add optional capabilities as needed:
pip install -e ".[templates]"   # Markdown / HTML output (Jinja2)
pip install -e ".[rag]"         # Chroma vector memory + RAG (chromadb)
pip install -e ".[graph]"       # LangGraph orchestration tracing layer
pip install -e ".[local-llm]"   # On-machine LLM via Ollama
pip install -e ".[bedrock]"     # Amazon Bedrock provider (boto3)
pip install -e ".[cloud]"       # Anthropic Claude provider
pip install -e ".[ui]"          # NiceGUI web dashboard
```

| Extra | Package installed | When you need it |
|---|---|---|
| `[templates]` | `jinja2>=3.1` | `--format markdown`, `--format plan`, `--format html` |
| `[rag]` | `chromadb>=0.5` | Chroma vector memory for RAG-enriched rationale |
| `[graph]` | `langgraph>=0.2` | LangGraph tracing/visualisation layer (optional) |
| `[local-llm]` | `ollama>=0.3` | Ollama on-machine LLM |
| `[bedrock]` | `boto3>=1.35` | AWS Bedrock Converse API provider |
| `[cloud]` | `anthropic>=0.40` | Anthropic Claude provider |
| `[ui]` | `nicegui>=2.0` | `rrr-ui` web dashboard |
| `[dev]` | pytest, ruff, mypy, hypothesis | Developer/CI toolchain |

---

## Quick start

```powershell
# 1. Install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,templates]"

# 2. Convert RKT HTML reports to brain data
rrr-ingest --html-dir input/ --brain-dir brain/ --value-stream "OSM"

# 3. Check what dimension data you still need
rrr-collect --status

# 4. Collect any missing dimension data interactively
rrr-collect --release "RetirePlus RC/RCP Enrollment" --all

# 5. Run the assessment
rrr --release "RetirePlus RC/RCP Enrollment" --config configs/osm.yaml

# Output:
# VERDICT: CONDITIONAL  SCORE: 74  CONFIDENCE: 88%

# 6. Try the demo (no real data needed)
rrr --release "Launch 36 - Unified Onboarding" --config configs/demo.yaml
```

---

## The four CLI tools

### `rrr` — assess a release

The primary tool. Takes a release name, runs all configured assessors, and outputs a
verdict.

```
rrr [OPTIONS]
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--release TEXT` | string | — | Release `ir_name` to assess. Supports fuzzy/partial matching. **Required** unless `--list-releases`. |
| `--config PATH` | file | — | Optional YAML config file, merged over bundled defaults. |
| `--value-stream TEXT` | string | from config | Override the configured value stream. |
| `--programme TEXT` | string | — | Filter to a specific programme (e.g. `OSM`, `AIMS`, `PIMS`). Scopes `--list-releases` and narrows fuzzy matching. |
| `--tier [hotfix\|standard\|major]` | choice | — | Release risk tier — selects a different threshold set from config. |
| `--format [text\|json\|markdown\|plan\|html]` | choice | `text` | Output format. |
| `--verbose` | flag | off | Emit full JSON (shorthand for `--format json`). |
| `--dry-run` | flag | off | Run the full pipeline but do not persist to SQLite. |
| `--list-releases` | flag | off | List all available releases in the brain file and exit. |

**Exit codes:**

| Code | Verdict |
|---|---|
| `0` | GO |
| `1` | NO_GO |
| `2` | CONDITIONAL |
| `3` | INCOMPLETE or ERROR |

**Examples:**

```powershell
# Standard text output
rrr --release "RetirePlus RC/RCP Enrollment" --config configs/osm.yaml

# Full JSON with all dimension details
rrr --release "RetirePlus RC" --config configs/osm.yaml --format json

# Markdown report (requires pip install rrr[templates])
rrr --release "RetirePlus RC" --format markdown > report.md

# Remediation action-plan checklist
rrr --release "RetirePlus RC" --format plan

# Self-contained HTML report
rrr --release "RetirePlus RC" --format html > report.html

# Assess as a hotfix (relaxed thresholds)
rrr --release "RetirePlus RC" --tier hotfix

# See all available releases in a value stream
rrr --list-releases --value-stream "OSM" --config configs/osm.yaml

# List releases for one programme only
rrr --list-releases --programme "AIMS" --config configs/osm.yaml

# Dry-run: full pipeline, no SQLite write
rrr --release "RetirePlus RC" --dry-run
```

---

### `rrr-ingest` — convert RKT HTML reports

Converts the HTML reports exported from the **RKT Program Metrics** system into the
`brain/*.json` snapshot format that `rrr` reads.

```
rrr-ingest [OPTIONS]
```

| Option | Required | Description |
|---|---|---|
| `--html-dir PATH` | Yes | Directory containing RKT HTML report files. |
| `--brain-dir PATH` | Yes | Output directory for brain JSON history files (created if absent). |
| `--value-stream TEXT` | Yes | Value-stream name used as the brain file prefix (e.g. `OSM`). |
| `--verbose` | No | Enable DEBUG logging. |

**How it works:**

- Each HTML file in `--html-dir` is parsed for the embedded `const __REPORT__` JSON
  that the RKT system injects into its export.
- Release metadata, story-point metrics, quality scores, E2E pass rates, defect
  counts, and dependency information are extracted and mapped to the brain contract.
- Results are written as dated snapshots to
  `<brain-dir>/<value-stream>-history.json`.
- Running the same file twice is safe — it does an idempotent upsert on snapshot date.

```powershell
# Process all HTML files in the input/ directory
rrr-ingest --html-dir input/ --brain-dir brain/ --value-stream "OSM"

# With debug logging
rrr-ingest --html-dir input/ --brain-dir brain/ --value-stream "OSM" --verbose
```

---

### `rrr-collect` — collect dimension data interactively

Populates the dimension JSON files in `data/` that are not derived from brain data.
These cover the 14 supplementary dimensions (environment, operability, security, etc.)
that release managers enter from their own systems.

```
rrr-collect [OPTIONS]
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--status` | | off | Print a traffic-light per dimension (FRESH / STALE / MISSING) and exit. Exits `0` if all fresh, `2` if any stale or missing. |
| `--dimension TEXT` | `-d` | — | Collect one named dimension interactively. |
| `--all` | | off | Collect all dimensions registered for the given tier. |
| `--release TEXT` | `-r` | — | Release name (IR name). Required for `--dimension` and `--all`. |
| `--tier [hotfix\|standard\|major]` | | standard | Controls which dimensions are required. Hotfix skips accessibility and architecture dims. |
| `--refresh` | | off | Overwrite existing files even when FRESH. |
| `--skip-optional` | | off | Accept defaults for non-required fields without prompting. |
| `--data-dir PATH` | | `data` | Directory for `<dimension>.json` files. |

**The 14 collectable dimensions:**

| Dimension | What it captures |
|---|---|
| `operability` | Runbooks, deployment checklist, operational gates |
| `observability` | Monitoring coverage, alerting health, dashboard availability |
| `rollback` | Rollback plan existence, test status, estimated time |
| `security` | SAST/DAST results, CVE counts, licence approvals |
| `performance` | Load test status, p99 latency vs SLO, capacity headroom |
| `accessibility` | WCAG compliance status, audit results |
| `auditability` | Audit log completeness, tamper-evidence, retention |
| `disaster_recovery` | DR plan, RTO/RPO targets, last DR test date |
| `data_reconciliation` | Data integrity checks, reconciliation status |
| `failure_mode` | FMEA coverage, critical failure modes documented |
| `dependency_risk` | External dependency vulnerability posture |
| `production_readiness` | Feature flags, DB migrations, rollout plan |
| `architecture_fitness` | Fitness function results, architectural constraint compliance |
| `architecture_drift` | Code-vs-architecture alignment score |

**Note:** `scope`, `estimation`, `test_readiness`, and `dependency` come from brain data
(via `rrr-ingest`) and are not in the collector registry.

**Examples:**

```powershell
# Check what's fresh, stale, or missing before a release
rrr-collect --status

# Collect everything for a standard release
rrr-collect --release "RetirePlus RC" --all

# Collect only the security dimension
rrr-collect --release "RetirePlus RC" --dimension security

# Hotfix — skip non-critical dimensions
rrr-collect --release "RetirePlus RC" --all --tier hotfix

# Refresh stale environment data
rrr-collect --release "RetirePlus RC" --dimension operability --refresh
```

**Programmatic adapters (library use):**

Three tool adapters are available in `src/rrr/collectors/adapters/` for pulling data
from CI/CD tools without interactive prompts:

| Adapter | What it reads | Input |
|---|---|---|
| `K6Adapter` | k6 `--summary-export` JSON file | `PerformanceInput` fields |
| `SnykAdapter` | `snyk test --json` subprocess output | `SecurityInput` fields |
| `SonarQubeAdapter` | SonarQube `/api/issues/search` REST API | `SecurityInput` fields |

```python
from rrr.collectors.adapters import K6Adapter, SnykAdapter, SonarQubeAdapter
from rrr.collectors.base import CollectorConfig
from rrr.collectors.runner import CollectorRunner

config = CollectorConfig(release="RetirePlus RC", data_dir="data")

# Pull performance data from a k6 summary file
adapter = K6Adapter(summary_path="k6-summary.json")
result = adapter.collect(config)

# Run through CollectorRunner to validate and write to data/performance.json
runner = CollectorRunner()
from rrr.models.performance import PerformanceInput
runner.run("performance", adapter, config, PerformanceInput)
```

---

### `rrr-ui` — web dashboard

Launches a local NiceGUI web dashboard for browsing releases, running assessments, and
visualising trends. **Requires** `pip install "rrr[ui]"`.

```
rrr-ui [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--config PATH` | — | Optional config YAML merged over bundled defaults. |
| `--port N` | 8080 | TCP port for the web server. |
| `--host HOST` | `127.0.0.1` | Network interface to bind (local only by default). |
| `--no-browser` | off | Do not open a browser tab automatically on startup. |

```powershell
pip install -e ".[ui]"

# Start on default port
rrr-ui

# With a specific config and port
rrr-ui --config configs/osm.yaml --port 9090

# Headless (no browser tab)
rrr-ui --no-browser
```

**Dashboard screens:**

| Screen | What it shows |
|---|---|
| **Overview** | 4-stat summary tile (total / NO-GO / CONDITIONAL / unassessed) + sortable release table, sorted by urgency (NO_GO first) |
| **Release Detail** | Verdict hero → dimension scorecard (score + trend arrow) → risk factors → rationale → remediation → environment/dependency/security data → assessment history |
| **History** | Cross-release activity feed, filterable by programme and TOC value stream |
| **Trends** | ECharts score-over-time line chart with GO/NO_GO threshold lines, per release |
| **Collect** | FRESH/STALE/MISSING status view + InputContract-driven forms per dimension, saving via the same `CollectorRunner` write path |

The dashboard auto-scans `brain/` for `*-history.json` files. When multiple brain files
exist (multiple value streams), a dataset picker appears in the header.

---

## Configuration reference

RRR uses a layered YAML configuration. The bundled `default_config.yaml` provides
production defaults; any user-supplied file is **merged over** (deep merge) the defaults
so you only need to set what changes.

```powershell
# Use a custom config
rrr --release "..." --config configs/osm.yaml

# The merger means configs/osm.yaml only needs to override sources.brain.value_stream etc.
```

### Full configuration schema

```yaml
schema_version: "1.0.0"

# ── Dimension weights (must sum to 1.0) ────────────────────────────────────────
weights:
  test_readiness: 0.27   # largest weight — test quality is the strongest gate signal
  scope:          0.23
  environment:    0.18
  dependency:     0.13
  estimation:     0.09
  operability:    0.07
  observability:  0.03   # opt-in only; set to 0.00 if not configured

# ── Verdict bands and robustness guards ────────────────────────────────────────
thresholds:
  go:                  0.80   # score >= go → GO (unless gate caps it)
  no_go:               0.40   # score < no_go → NO_GO
  minimum_assessors:   4      # fewer available → INCOMPLETE
  required_dimensions: [test_readiness, environment]   # must succeed → else CONDITIONAL
  confidence_floor:    0.70   # aggregate confidence below this → cap to CONDITIONAL

# ── Trend comparison deltas ────────────────────────────────────────────────────
trend:
  improving_delta:  0.05    # dimension score rose ≥ 5% → ↑ improving
  degrading_delta: -0.05    # dimension score fell ≥ 5% → ↓ degrading

# ── Verdict veto / cap gates ───────────────────────────────────────────────────
gates:
  enabled:                true
  e2e_critical_floor:     0.50   # e2e pass rate below this → CRITICAL
  blocker_defects:        NO_GO
  critical_defects_limit: 0      # any critical defects → CRITICAL risk factor
  environment_down:       NO_GO
  environment_degraded:   CONDITIONAL
  dependency_failed:      NO_GO
  dependency_blocking:    CONDITIONAL
  scope_creep_threshold:  0.10   # scope delta > 10% → MAJOR risk factor

# ── Timeouts in seconds ────────────────────────────────────────────────────────
timeouts:
  assessor_default:    300   # per-assessor wall-clock timeout (ThreadPoolExecutor)
  environment_source:   60   # environment / dependency source read
  external_source:      10   # any other external source
  tool_default:         30   # per tool invocation

# ── SQLite persistence retry ───────────────────────────────────────────────────
persistence:
  retry_attempts:         3
  retry_interval_seconds: 5

# ── Tool invocation retry ──────────────────────────────────────────────────────
tools:
  retry_count:    1     # retries on transient ToolInvocationError (not timeout)
  retry_backoff_s: 0.5

# ── LLM provider ──────────────────────────────────────────────────────────────
provider:
  type: rule_based          # rule_based | local_llm | mock_llm | bedrock | claude
  repair_retries: 1         # structured-output repair attempts before fallback

  # Uncomment the block for your chosen provider:

  # local_llm:
  #   endpoint: "http://127.0.0.1:11434"
  #   model: "llama3.1"

  # mock_llm:
  #   fixture_dir: "tests/fixtures/llm_responses"

  # bedrock:
  #   model_id: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  #   region: "us-east-1"
  #   max_tokens: 1024
  #   temperature: 0.1

  # claude:
  #   model: "claude-sonnet-4-6"
  #   max_tokens: 1024
  #   temperature: 0.1

# ── Data sources ───────────────────────────────────────────────────────────────
sources:
  brain:
    dir: "./brain"
    value_stream: "Retirement-Services"
    snapshot: "latest"           # "latest" or an ISO date string e.g. "2026-06-08"

  # Core supplementary dimensions (always required):
  environment: { type: file, path: "./data/environment.json" }
  dependency:  { type: file, path: "./data/dependency.json" }
  operability: { type: file, path: "./data/operability.json" }

  # Optional weighted dimension:
  # observability: { type: file, path: "./data/observability.json" }

  # Optional gate-only dimensions (uncomment to activate):
  # rollback:            { type: file, path: "./data/rollback.json" }
  # security:            { type: file, path: "./data/security.json" }
  # performance:         { type: file, path: "./data/performance.json" }
  # accessibility:       { type: file, path: "./data/accessibility.json" }
  # auditability:        { type: file, path: "./data/auditability.json" }
  # disaster_recovery:   { type: file, path: "./data/disaster_recovery.json" }
  # data_reconciliation: { type: file, path: "./data/data_reconciliation.json" }
  # failure_mode:        { type: file, path: "./data/failure_mode.json" }
  # dependency_risk:     { type: file, path: "./data/dependency_risk.json" }
  # production_readiness:{ type: file, path: "./data/production_readiness.json" }
  # architecture_fitness:{ type: file, path: "./data/architecture_fitness.json" }
  # architecture_drift:  { type: file, path: "./data/architecture_drift.json" }

  # Sources can also point to local HTTP APIs (local-first: must be 127.0.0.1/localhost):
  # environment: { type: api, url: "http://127.0.0.1:8000/api/v1/environment" }

  allowed_hosts: ["127.0.0.1", "localhost"]   # enforced at runtime; no other hosts allowed

# ── Assessor-specific knobs ────────────────────────────────────────────────────
assessors:
  test_readiness:
    suite_pass_threshold: 0.80     # < 80% pass rate → CRITICAL
    weights: { quality: 0.4, defect_trend: 0.3, e2e_pass_rate: 0.3 }
    e2e_absent: renormalize        # "renormalize" or "zero"
    freshness_max_age_days: 30     # test data older than this → MINOR confidence hit
  security:
    high_cve_threshold: 5          # ≥ this many high CVEs → MAJOR risk factor

# ── Release risk tiers ─────────────────────────────────────────────────────────
tiers:
  hotfix:
    go: 0.60
    no_go: 0.30
    confidence_floor: 0.60
    required_gate_dims: [test_readiness]
    excluded_gate_dims: []
  standard:
    go: 0.80
    no_go: 0.40
    confidence_floor: 0.70
    required_gate_dims: [test_readiness, environment]
    excluded_gate_dims: []
  major:
    go: 0.90
    no_go: 0.60
    confidence_floor: 0.80
    required_gate_dims: [test_readiness, environment, dependency]
    excluded_gate_dims: []

# ── Memory and RAG ─────────────────────────────────────────────────────────────
memory:
  sqlite_path: "./data/local/rrr.sqlite"
  chroma_path: null       # set a directory path to enable Chroma RAG
  rag_top_k: 3            # number of similar past assessments to retrieve
```

### Environment-variable interpolation

Config values can reference environment variables using `${VAR_NAME}` syntax:

```yaml
provider:
  claude:
    model: "${CLAUDE_MODEL}"

memory:
  sqlite_path: "${DATA_DIR}/rrr.sqlite"
```

Variables are substituted before Pydantic validation. Missing variables raise a
`ConfigurationError`.

### HTTP Basic Auth for the web dashboard

```yaml
ui:
  auth_user: "admin"
  auth_password: "${UI_PASSWORD}"   # set via environment variable
```

Both fields must be set together or both omitted (no partial auth config).

---

## Data sources

### Brain data (RKT snapshots)

Brain data comes from **RKT Program Metrics** HTML exports, converted by `rrr-ingest`.

```
brain/
  OSM-history.json          ← all dated snapshots for the OSM value stream
  Retirement-Services-history.json
```

Each entry in the history file is a dated snapshot covering all releases visible in that
report. `rrr` defaults to `snapshot: latest` but you can pin to a specific date:

```yaml
sources:
  brain:
    dir: "./brain"
    value_stream: "OSM"
    snapshot: "2026-06-08"   # pin to a specific export date
```

The **brain contract** captures per-release:
- Story points: planned, completed, velocity, burn-down trajectory
- Quality scores (0–3 scale)
- E2E test pass rates
- Defect counts by severity
- Scope-creep history (week-over-week changes)
- Environment provisioning and stability
- Dependency completion and integration status
- Release relationships (dependency_for, enables_release)
- Programme code and TOC value stream tag

### Dimension data files

Files in `data/` supply the supplementary dimensions. Use `rrr-collect` to populate
them interactively, or write them directly.

Each file is a JSON object whose keys match the corresponding `InputContract` model.
`rrr-collect --status` tells you which files are FRESH (< 24h), STALE (> 24h), or MISSING.

**Minimum required files (always needed):**

```
data/environment.json       ← environment provisioning and stability state
data/dependency.json        ← inter-release dependency completion status
data/operability.json       ← operational readiness (runbooks, deployment checklist)
```

**Optional files (activate by uncommenting in config):**

```
data/observability.json     ← monitoring and alerting coverage
data/rollback.json          ← rollback plan and test status
data/security.json          ← SAST/DAST results, CVE counts
data/performance.json       ← load test results, p99 latency, SLO
data/accessibility.json     ← WCAG audit results
data/auditability.json      ← audit log completeness
data/disaster_recovery.json ← DR plan, RTO/RPO, last test date
data/data_reconciliation.json
data/failure_mode.json
data/dependency_risk.json
data/production_readiness.json
data/architecture_fitness.json
data/architecture_drift.json
```

See [docs/assessor_inputs.md](docs/assessor_inputs.md) for the full field reference per
dimension.

---

## Assessors

Assessors are independent agents that each evaluate one release readiness dimension.
They run in **parallel** (ThreadPoolExecutor). A timed-out or erroring assessor becomes
`unavailable` — its weight is redistributed proportionally across the remaining assessors
so the score stays comparable (graceful degradation).

### Core scored dimensions

These always run and contribute to the numeric score.

| Assessor | Weight | Source | What it measures |
|---|---|---|---|
| **TestReadiness** | 0.27 | brain | Test suite pass rate, E2E pass rate, defect trend, data freshness |
| **Scope** | 0.23 | brain | Story-point completion ratio, scope-creep week-over-week drift |
| **Environment** | 0.18 | brain + `data/environment.json` | Provisioning completeness, stability grade, component health |
| **Dependency** | 0.13 | brain + `data/dependency.json` | Inter-release dependency completion and integration status |
| **Estimation** | 0.09 | brain | Velocity stability, planned-vs-actual earned-value accuracy |
| **Operability** | 0.07 | `data/operability.json` | Runbook coverage, deployment checklist gates, operational readiness |
| **Observability** _(opt-in)_ | 0.03 | `data/observability.json` | Monitoring coverage, alerting health, dashboard availability |

### Gate-only dimensions

Gate-only assessors produce risk factors that can **cap the verdict** (CRITICAL → NO_GO,
MAJOR → CONDITIONAL) but do not contribute to the numeric score. They are all opt-in —
activate by adding the source to your config.

| Assessor | Gate effect | Typical triggers |
|---|---|---|
| **Rollback** | CONDITIONAL (no plan) | Missing rollback runbook or untested plan |
| **Security** | NO_GO (critical CVEs), CONDITIONAL (high CVEs) | SAST failures, unresolved critical/high CVEs |
| **Performance** | NO_GO (test failed / severe latency), CONDITIONAL (SLO breach) | Load test failure, p99 > 2× SLO |
| **Accessibility** | CONDITIONAL | WCAG failures |
| **Auditability** | CONDITIONAL | Incomplete audit log coverage |
| **DisasterRecovery** | NO_GO (no plan), CONDITIONAL (untested) | Missing DR plan, overdue DR test |
| **DataReconciliation** | NO_GO (broken), CONDITIONAL (partial) | Data integrity check failures |
| **FailureMode** | CONDITIONAL | Critical failure modes undocumented |
| **DependencyRisk** | NO_GO (critical vuln), CONDITIONAL (high vuln) | Vulnerable external dependencies |
| **ProductionReadiness** | CONDITIONAL | Missing feature flags, unrun DB migrations |
| **ArchitectureFitness** | CONDITIONAL | Fitness function failures |
| **ArchitectureDrift** | CONDITIONAL | Code-vs-architecture alignment below threshold |

---

## LLM providers

The LLM provider writes the dimension narrative, risk rationale, and remediation plan.
It **never** influences the numeric score or verdict label.

| Provider | Config `type` | Package | Notes |
|---|---|---|---|
| **RuleBasedProvider** | `rule_based` | _(none)_ | Deterministic, no model. Default. Ideal for CI or air-gapped use. |
| **LocalLLMProvider** | `local_llm` | `rrr[local-llm]` | Ollama on `127.0.0.1`. Set `endpoint` and `model` in config. |
| **MockLLMProvider** | `mock_llm` | _(none)_ | Fixture-backed, for demos and tests. Set `fixture_dir`. |
| **BedrockProvider** | `bedrock` | `rrr[bedrock]` | AWS Bedrock Converse API. Set `model_id` and `region`. Requires AWS credentials. |
| **ClaudeProvider** | `claude` | `rrr[cloud]` | Anthropic Messages API. Set `ANTHROPIC_API_KEY` env var. |

All providers go through the same **guardrail chain**:
1. Provider generates raw output.
2. Output is validated against a Pydantic schema.
3. On validation failure, a repair hint is sent and the provider retries once.
4. If repair fails, `RuleBasedProvider` is used as fallback and confidence is capped.

**Local-only Ollama setup:**

```powershell
# Install Ollama from https://ollama.com then:
ollama pull llama3.1

pip install -e ".[local-llm]"
```

```yaml
# In your config.yaml:
provider:
  type: local_llm
  local_llm:
    endpoint: "http://127.0.0.1:11434"
    model: "llama3.1"
```

**Claude (Anthropic) setup:**

```powershell
pip install -e ".[cloud]"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

```yaml
provider:
  type: claude
  claude:
    model: "claude-sonnet-4-6"
```

---

## Output formats

| Format | Flag | Notes |
|---|---|---|
| **text** (default) | _(none)_ | `VERDICT: GO  SCORE: 84  CONFIDENCE: 91%  TIER: STANDARD` |
| **json** | `--format json` or `--verbose` | Full `AssessmentOutputModel` as pretty-printed JSON |
| **markdown** | `--format markdown` | Jinja2-rendered report with dimension breakdown and risk table. Requires `rrr[templates]`. |
| **plan** | `--format plan` | Action-plan checklist: CRITICAL/MAJOR/MINOR-bucketed remediation items with `- [ ]` checkboxes. Requires `rrr[templates]`. |
| **html** | `--format html` | Self-contained Bootstrap 5 HTML report (CDN links). Requires `rrr[templates]`. |

**JSON output structure:**

```json
{
  "release":                 "RetirePlus RC/RCP Enrollment",
  "value_stream":            "OSM",
  "verdict":                 "CONDITIONAL",
  "score":                   74,
  "aggregate_confidence":    0.88,
  "tier":                    "standard",
  "ship_safety_score":       71,
  "delivery_performance_score": 82,
  "generated_at":            "2026-07-26T10:30:00.000Z",
  "dimensions": [
    {
      "dimension":   "test_readiness",
      "score":       0.71,
      "confidence":  0.90,
      "status":      "available",
      "trend":       "degrading",
      "risk_factors": [
        { "description": "E2E pass rate 64% below 80% threshold", "severity": "MAJOR", "gate": "..." }
      ],
      "narrative":   "Test readiness is borderline ...",
      "evidence":    { ... }
    }
  ],
  "rationale":     "The release scores 74/100 overall ...",
  "remediation":   "Priority 1: Address the E2E failure rate ...",
  "tool_invocations": [ ... ]
}
```

---

## Release risk tiers

Different release types carry different risk. Use `--tier` to select the appropriate
threshold set:

| Tier | `--tier` flag | GO threshold | NO_GO threshold | Required dims |
|---|---|---|---|---|
| **Standard** (default) | `standard` | ≥ 0.80 | < 0.40 | test_readiness, environment |
| **Hotfix** | `hotfix` | ≥ 0.60 | < 0.30 | test_readiness |
| **Major** | `major` | ≥ 0.90 | < 0.60 | test_readiness, environment, dependency |

Gate-only assessors are unaffected by tier unless listed in `excluded_gate_dims` in the
tier config.

All three tier threshold sets are defined in the `tiers:` block of `default_config.yaml`
and can be overridden per value stream.

---

## Scoring and verdict logic

**Score computation:**

```
weighted_score = Σ (dimension_score × redistributed_weight)
```

Weight redistribution: if a dimension is `unavailable` (timeout, missing data, error),
its weight is spread proportionally across the remaining available dimensions so the
score stays on a comparable scale.

**Verdict derivation (in priority order):**

1. If fewer than `minimum_assessors` dimensions are available → **INCOMPLETE**
2. If a CRITICAL risk factor exists → **NO_GO** (gate cap)
3. If a MAJOR risk factor exists → at most **CONDITIONAL** (gate cap)
4. If a required dimension is missing/unavailable → at most **CONDITIONAL**
5. If aggregate confidence < `confidence_floor` → at most **CONDITIONAL**
6. Otherwise: score ≥ `go` → **GO** · score < `no_go` → **NO_GO** · otherwise → **CONDITIONAL**

**Sub-scores:**

`ship_safety_score` = test_readiness + environment + dependency + operability + observability
`delivery_performance_score` = scope + estimation

These appear in `--format text` output when a tier is specified and in the JSON output.

---

## Historical trends

Every non-dry-run assessment is persisted to SQLite (`data/local/rrr.sqlite`). The next
run for the same release compares against the previous result and computes a trend
direction per dimension:

| Symbol | Meaning |
|---|---|
| `↑ improving` | Score rose ≥ 0.05 |
| `↓ degrading` | Score fell ≥ 0.05 |
| `→ stable` | Score changed < 0.05 |

Trends appear in the JSON output (`"trend"` field per dimension) and in the `rrr-ui`
Release Detail scorecard.

**Optional Chroma RAG:** If `memory.chroma_path` is set, each assessment is also
embedded into a Chroma vector store (6D: [scope, estimation, environment,
test_readiness, dependency, score/100]). Similar historical releases are retrieved at
rationale-synthesis time to give the LLM provider richer context.

---

## Web dashboard

The `rrr-ui` dashboard (requires `pip install "rrr[ui]"`) provides a browser UI for
the same data the CLI surfaces. It does not replace the CLI — both tools share the same
SQLite store and config.

```powershell
pip install -e ".[ui]"
rrr-ui --config configs/osm.yaml
# → opens http://127.0.0.1:8080
```

**Collect screen:** The dashboard includes an interactive Collect screen that mirrors
`rrr-collect` — showing FRESH/STALE/MISSING status per dimension and providing form
fields driven by the same `InputContract` Pydantic models.

---

## Development

### Quality gate

All four steps must be green before committing:

```powershell
# 1. Comment coverage — every module, class, and public function must have a docstring
.venv\Scripts\python.exe scripts/check_comments.py src/rrr

# 2. Lint
.venv\Scripts\python.exe -m ruff check src tests

# 3. Type-check (strict)
.venv\Scripts\python.exe -m mypy src

# 4. Tests
.venv\Scripts\python.exe -m pytest

# Or run all four in one shot:
scripts\check_all.ps1
```

### Test structure

```
tests/
  unit/          42 test files — one per module, fast (< 1s each)
  property/      Hypothesis invariant tests (score bounds, weight redistribution, verdict determinism)
  golden/        5 end-to-end fixtures (g1=GO, g2=NO_GO, g3=CONDITIONAL, g4=INCOMPLETE, g5=CONDITIONAL)
  eval/          LLM evaluation harness (StructuralJudge + ProseQualityJudge)
  fixtures/      Mock LLM response JSON fixtures
```

Run targeted subsets:

```powershell
pytest tests/unit/                              # unit tests only
pytest tests/golden/                            # golden fixture E2E
pytest tests/unit/test_scope_assessor.py        # single module
pytest -m "not eval"                            # skip the LLM eval harness
```

### Alignment check

After any change to ADRs, diagrams, or source modules:

```powershell
.venv\Scripts\python.exe scripts/check_alignment.py
# Must print: ALIGNMENT: PASS — docs agree with reality
```

### Adding a new assessor

1. Create `src/rrr/assessors/<name>_assessor.py` extending `BaseAssessor`.
2. Create `src/rrr/models/<name>.py` with an `InputContract` subclass.
3. Add a `<name>SourceReader` to `src/rrr/tools/source_reader.py`.
4. Add a `data/<name>.json` stub.
5. Add opt-in wiring to `src/rrr/pipeline.py`.
6. Add tests in `tests/unit/test_<name>_assessor.py`.
7. Run the full quality gate.

See [src/rrr/assessors/](src/rrr/assessors/) and [.claude/rules/assessor-pattern.md](.claude/rules/assessor-pattern.md) for the full pattern.

---

## Project structure

```
src/rrr/
  assessors/      BaseAssessor ABC + 19 concrete assessors (7 weighted + 12 gate-only)
  collectors/     BaseCollector + CollectorRunner + CollectorRegistry + InteractiveCollector
    adapters/     K6Adapter · SnykAdapter · SonarQubeAdapter
  config/         ConfigLoader + default_config.yaml + Pydantic schema
  ingest/         HTMLExtractor + BrainWriter + rrr-ingest CLI
  memory/         AbstractAssessmentStore + SQLiteAssessmentStore (WAL + Chroma RAG)
  models/         24 Pydantic v2 model modules (one per domain)
  orchestration/  Orchestrator · GateEngine · scoring · verdict · trends · LangGraph wrapper
  output/         MarkdownRenderer · PlanRenderer · HtmlRenderer (Jinja2 templates)
  providers/      LLMProvider ABC + RuleBased · LocalLLM · MockLLM · Bedrock · Claude
  tools/          BaseTool protocol + ToolRunner + RKTBrainReader + 17 source readers
  ui/             NiceGUI dashboard (Overview · Release Detail · History · Trends · Collect)
  cli.py          Click entry point (rrr)
  pipeline.py     Composition root (assess · run_and_record · build_provider · build_store)
  errors.py       Typed error hierarchy

brain/            RKT snapshot history files (*-history.json)
configs/          Reference config overrides (demo · osm · claude · bedrock)
data/             Dimension JSON files + local/ (SQLite + Chroma)
docs/             Architecture · Requirements · Roadmap · Vision · Evaluation plan · AI usage log
diagrams/         10 Mermaid architecture diagrams
adr/              23 Architecture Decision Records
tests/            unit/ · property/ · golden/ · eval/ · fixtures/
scripts/          check_comments.py · check_alignment.py · check_all.ps1
```

---

## Status

**Phase 1 complete · Phase 2 complete · M1–M6 ✅ · M7 🔄**
_Last updated: 2026-07-26_

**766 tests** · comments + ruff + mypy + pytest green · alignment PASS (23 ADRs / 9 diagrams / 97 modules)

Golden fixture proof: **g1 → GO/97 · g2 → NO_GO · g3 → CONDITIONAL/74 · g4 → INCOMPLETE · g5 → CONDITIONAL/93**

| Milestone | Scope | Status |
|---|---|---|
| Design | docs, ADRs, diagrams, contracts | ✅ Complete |
| M1 | Foundations: models · config · tools · providers · BaseAssessor | ✅ Complete |
| M2 | Output layer: MarkdownRenderer · PlanRenderer · `--dry-run` | ✅ Complete |
| M3 | Core assessors + orchestrator → verdict | ✅ Complete |
| M4 | Persistence · trends · eval harness · CLI | ✅ Complete |
| M5 | Scale-out: ClaudeProvider · NiceGUI · live APIs · BedrockProvider | ✅ Complete |
| M6 | Assessment Model V2: risk tiers · OperationalAssessor split · 9 gate-only assessors | ✅ Complete |
| M7 | Data Collection: `rrr-collect` CLI · `rrr-ui` Collect screen · tool adapters | 🔄 In progress (adapters ⬜) |
