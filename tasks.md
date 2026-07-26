# RRR — Prioritised Task List
> Generated from ArchReview.md · 2026-07-09  
> Priority 1 = do now (blocks client engagement or risks data loss)  
> Priority 5 = strategic / longer-term  
> Each task states: what it is · why now · what value it adds

---

## Priority 1 — Immediate (do before anything else)

These tasks either block a first client engagement, present a data safety risk, or make the system
demonstrably broken under realistic usage. None takes more than 1–2 sessions.

---

### T-01 · OperationalAssessor Split (ADR-0016 item 7)
**Status:** Next committed action (roadmap pointer)  
**Layer:** `src/rrr/assessors/` · `src/rrr/config/schema.py` · `default_config.yaml`

**What it is:**  
Split the current `OperationalAssessor` (weight 0.10) into three independent assessors:
- `OperabilityAssessor` — deployment pipeline health, runbook presence (weight 0.07)
- `ObservabilityAssessor` — monitoring dashboards, alerting, trace coverage (weight 0.03)
- `RollbackAssessor` — rollback procedure tested and documented (gate-only, weight 0)

**Why now:**  
The current single assessor conflates three distinct risk signals with different data sources,
different tier requirements, and different gate behaviours. `RollbackAssessor` is listed as
required-for-all-tiers in `docs/assessor_inputs.md` but has no assessor code. The split is already
designed (ADR-0016 item 7, `docs/assessor_inputs.md` registry). Delaying it means the weight
rebalance (removing `operational: 0.10`) will need to be done later when more tests exist against
the current weights — more disruption.

**Value added:**  
- Closes ADR-0016 item 7
- Enables `RollbackAssessor` as a required gate for all tier types (a significant safety gate)
- Separates monitoring coverage (observability) from pipeline health (operability) — two genuinely different questions a release manager wants answered independently
- Weight sum stays 1.0 after rebalance (0.07 + 0.03 + existing 5 dims = 1.00)

---

### T-02 · Authentication on `rrr-ui`
**Status:** Not started  
**Layer:** `src/rrr/ui/app.py` · `src/rrr/config/schema.py`

**What it is:**  
Add HTTP Basic Auth (configurable user/password in `config.ui`) to the NiceGUI server startup.
NiceGUI exposes the underlying FastAPI app — middleware can be added directly.

```yaml
# default_config.yaml addition
ui:
  host: "127.0.0.1"
  port: 8080
  auth_user: null    # null = no auth (Phase 1 local use)
  auth_password: null
```

**Why now:**  
The dashboard currently has zero authentication. Any user who can reach the port sees all release
data, risk factors, security posture, and assessment history. On a shared developer network or a
client VPN, this is a data exposure incident waiting to happen. This is the first thing a client
security team will flag in a deployment review.

**Value added:**  
- Unblocks any networked client deployment
- No code complexity — NiceGUI's FastAPI base accepts standard ASGI middleware in two lines
- Lays the groundwork for the later RBAC and SSO integration (T-21)

---

### T-03 · SQLite WAL Mode
**Status:** Not started — one-line fix  
**Layer:** `src/rrr/memory/store.py`

**What it is:**  
Add `PRAGMA journal_mode=WAL` to `SQLiteAssessmentStore.__init__()` immediately after the
connection is established.

**Why now:**  
The current default SQLite journal mode (DELETE) places an exclusive write lock for the entire
duration of a write transaction. If two CLI invocations run concurrently against the same
database — which happens in any batch script or CI pipeline — one will wait for the lock and
potentially time out. The retry policy (`retry_attempts: 3`) buys 15 seconds, which is often not
enough. WAL mode allows concurrent readers + one writer, eliminating this class of failure entirely.

**Value added:**  
- Zero-downtime fix (WAL mode is automatically applied to an existing database)
- Eliminates the write contention risk for all multi-process CLI use patterns
- Required prerequisite before any server deployment where multiple requests can trigger writes

---

### T-04 · Secret Injection via Environment Variables
**Status:** Not started  
**Layer:** `src/rrr/config/loader.py`

**What it is:**  
Add `${ENV_VAR}` interpolation in `ConfigLoader.load()` — scan all string values in the merged
YAML dict and replace `${VAR_NAME}` patterns with `os.environ.get("VAR_NAME")` before Pydantic
validation.

```yaml
# Config would then safely support:
provider:
  type: claude
  claude:
    api_key: "${ANTHROPIC_API_KEY}"
```

**Why now:**  
The current design requires API keys (Claude, Bedrock, future SonarQube tokens) to be placed in
the YAML config file. In any team environment, YAML files get committed to version control. A
leaked API key in a client repository is a security incident. Kubernetes-native deployments always
inject secrets via environment variables — the current design blocks this pattern entirely.

**Value added:**  
- Enables Kubernetes Secrets and AWS Secrets Manager integration immediately
- Prevents accidental API key exposure in version control
- Required for any CI/CD or containerised deployment model

---

### T-05 · Trends Tab Assessment Caching
**Status:** Not started — performance blocker  
**Layer:** `src/rrr/memory/store.py` · `src/rrr/ui/app.py`

**What it is:**  
Two changes:
1. Add a `get_or_compute(release, snapshot_date, compute_fn)` method to `SQLiteAssessmentStore`
   that checks for a cached assessment record by `(release, snapshot_date)` before running
   the full pipeline.
2. In `score_over_snapshots()` in `ui/app.py`, call the cached path instead of re-running
   `pipeline.assess()` for each snapshot.

**Why now:**  
The current Trends tab runs a full pipeline assessment for every (release × snapshot) combination
on every render. For a realistic programme (40 releases × 52 weekly snapshots), this is 2,080
mini-assessments per page load — approximately 17 minutes of computation. The tab is effectively
unusable for any client with more than a few months of history. This will be the first thing a
client notices when they open the dashboard.

**Value added:**  
- Trends tab renders in < 1 second after first load (reading from SQLite vs re-computing)
- Eliminates the NiceGUI event loop blocking during trend computation
- The cache is already correct by construction — `RuleBasedProvider` + same data = same result

---

## Priority 2 — Short-Term (production readiness, ≤ 4 weeks)

These tasks are needed before any production or client-facing deployment. They address structural
gaps that will be noticed in an operational review.

---

### T-06 · Structured Logging (replace `print()`)
**Status:** Not started  
**Layer:** `src/rrr/pipeline.py` · `src/rrr/cli.py` · all assessors

**What it is:**  
Replace all `print()` and `click.echo()` diagnostic calls with `logging.getLogger("rrr.*")`
calls. Add a `correlation_id` (UUID per assessment run) to all log records. Add this ID to
`AuditTrail`. Emit JSON-formatted logs when `--format json` is active.

**Why now:**  
Without structured logging, an operations team cannot:
- Filter logs by assessment run in a log aggregation system (Splunk, CloudWatch, Datadog)
- Alert on provider fallback rate > threshold
- Trace a single failed assessment through the full log stream

It is also the gap between a demo tool and a production system in any client technology review.

**Value added:**  
- Enables log-based monitoring and alerting without code changes
- `correlation_id` in `AuditTrail` ties every log line to the assessment that produced it
- Provides the observability foundation that T-22 (OpenTelemetry) builds on

---

### T-07 · SQLite Schema Migration Guard
**Status:** Not started  
**Layer:** `src/rrr/memory/store.py`

**What it is:**  
Add `PRAGMA user_version = N` tracking to `SQLiteAssessmentStore`. On open, read the current
`user_version`. If it is below the expected version, run migration SQL (e.g., `ALTER TABLE
assessments ADD COLUMN tier TEXT`). Bump `user_version` after each successful migration.

**Why now:**  
The M6 tier fields (`tier`, `ship_safety_score`, `delivery_performance_score`) were added to
`AssessmentOutputModel` in this milestone. Any existing SQLite database created before this
milestone will fail to deserialise old records if the document JSON is missing these fields. This
is a silent data corruption risk. The first client to upgrade from an older version will lose their
assessment history.

**Value added:**  
- Existing assessment databases survive version upgrades without data loss
- Standard engineering practice for any persistent store — its absence is a code review finding
- Required before the first client hands over their data to the system

---

### T-08 · `rrr export` Backup Command
**Status:** Not started  
**Layer:** `src/rrr/cli.py` · `src/rrr/memory/store.py`

**What it is:**  
Add `rrr export --format jsonl --output backup.jsonl` CLI command that streams all assessment
records from the SQLite store to a newline-delimited JSON file. Each line is a complete
`AssessmentOutputModel` JSON object.

**Why now:**  
The SQLite database is the only copy of all historical assessment data. There is no backup
mechanism, no export, and no mention of backup in the deployment guide. A corrupted or
accidentally deleted SQLite file means permanent loss of all programme history — the audit trail,
the trend data, and the benchmark data. This is a data governance gap that any client data team
will flag immediately.

**Value added:**  
- Simple disaster recovery: `rrr export` nightly via cron → offsite storage
- Enables offline analytics (pipe the JSONL to pandas/Spark for deeper analysis)
- A prerequisite for the future PostgreSQL migration path (T-23)
- Demonstrates responsible data stewardship in client conversations

---

### T-09 · Health Endpoint for `rrr-ui`
**Status:** Not started  
**Layer:** `src/rrr/ui/app.py` (or `src/rrr/ui/_cli.py`)

**What it is:**  
Add a `/health` HTTP endpoint to the NiceGUI server that returns:
```json
{ "status": "ok", "sqlite": "connected", "provider": "rule_based", "version": "1.0.0" }
```
NiceGUI uses FastAPI internally — a custom route can be added via `app.add_route()`.

**Why now:**  
Without a health endpoint, there is no way for a load balancer, Kubernetes liveness probe, or
monitoring system to determine whether the server is running and healthy. Any containerised or
Kubernetes deployment will fail its readiness check.

**Value added:**  
- Enables Kubernetes liveness/readiness probes (required for T-25 Helm chart)
- Enables uptime monitoring alerts via any HTTP checker
- Zero complexity — five lines of code

---

### T-10 · Session-Scoped `ToolResultCache`
**Status:** Not started  
**Layer:** `src/rrr/orchestration/orchestrator.py` · `src/rrr/tools/runner.py`

**What it is:**  
Add a `ToolResultCache` context manager that wraps `ToolRunner.run()` within a single assessment
session. Keys are `(tool_name, params_hash)`. Cache hit returns the stored `ToolRunResult`
without invoking the tool again. Context manager scope ensures the cache is discarded after each
assessment.

**Why now:**  
Currently, if 50 releases are assessed in sequence (e.g., batch mode or `score_over_snapshots()`),
`environment.json` is read once per release — 50 file reads of the same file. When source APIs
are involved, this becomes 50 HTTP calls to the same endpoint for shared programme-level data.
Redundant I/O is the primary cost in any batch assessment scenario.

**Value added:**  
- Eliminates redundant source reads within a batch assessment run
- Reduces assessment batch time in proportion to the number of shared source reads
- Prerequisite for performant `rrr-collect --all` batch mode (T-13)

---

### T-11 · Nine New Gate-Only Assessors (ADR-0016 items 8–16)
**Status:** Not started — planned, input contracts defined in `docs/assessor_inputs.md`  
**Layer:** `src/rrr/assessors/` · `src/rrr/models/` · `tests/unit/`

**What it is:**  
Build the nine remaining gate-only assessors (all weight=0, verdict impact via CRITICAL/MAJOR
risk factors only):

| # | Assessor | Primary Gate Signal |
|---|----------|---------------------|
| 8 | `AccessibilityAssessor` | WCAG compliance gate — CRITICAL if fail |
| 9 | `AuditabilityAssessor` | Audit log completeness, compliance artefacts |
| 10 | `DisasterRecoveryAssessor` | DR test passed, RTO/RPO validated |
| 11 | `DataReconciliationAssessor` | Migration row counts, checksums (opt-in) |
| 12 | `FailureModeAssessor` | FMEA completion, chaos test outcomes |
| 13 | `DependencyRiskAssessor` | Third-party risk register, SLA coverage |
| 14 | `ProductionReadinessAssessor` | Runbook completeness, on-call roster |
| 15 | `ArchitectureFitnessAssessor` | Architecture rule violations (ArchUnit) |
| 16 | `ArchitectureDriftAssessor` | Drift from intended design (Backstage, git) |

Each requires: `InputContract` model, `SourceReader`, assessor class, unit tests vs a golden fixture.

**Why now:**  
These nine assessors are the difference between a tool that assesses "can we ship the code?" and a
tool that assesses "is the organisation ready to operate this release?" For enterprise clients
(government, financial services), Accessibility, DR, and Auditability are non-negotiable governance
requirements. Without them, RRR cannot be presented as a complete governance platform.

**Value added:**  
- Closes ADR-0016 items 8–16 and completes M6
- Each assessor adds a hard veto capability (CRITICAL risk → NO_GO) for its domain
- Transforms the tool from a delivery-completeness check to a full release governance platform
- Directly enables Model B and Model C client engagement models (§4.3 of ArchReview.md)

---

### T-12 · Bundle Bootstrap CSS (remove CDN dependency)
**Status:** Not started — one-line-equivalent change  
**Layer:** `src/rrr/output/templates/verdict_report.html.j2` (or equivalent)

**What it is:**  
Replace the Bootstrap CDN `<link>` tag in the HTML output template with an inlined or locally
bundled Bootstrap CSS. The minified Bootstrap 5.3 CSS is ~32 KB — acceptable to inline.

**Why now:**  
`--format html` currently loads Bootstrap from `cdn.jsdelivr.net`. This breaks in any client
environment with strict Content Security Policy, no internet access (airgapped), or a corporate
web proxy that blocks CDNs. It also violates ADR-0010 (no external network calls at runtime) —
the HTML renderer makes an outbound call on behalf of the user every time the HTML is opened.

**Value added:**  
- Self-contained HTML output — works in airgapped environments
- Eliminates a security finding in any CSP audit
- ADR-0010 compliance for the output layer

---

## Priority 3 — Medium-Term (client asset quality, ~1–2 months)

These tasks elevate the tool from a working prototype to a credible client-deliverable asset.

---

### T-13 · `rrr-collect` CLI and Collector Layer (ADR-0023)
**Status:** Proposed (2026-07-04) — not yet designed  
**Layer:** `src/rrr/collectors/` (new) · `src/rrr/cli.py` · `src/rrr/ui/app.py`

**What it is:**  
Implement the data collection automation layer:
- `BaseCollector` ABC: `collect(release, config)` → `InputContract` · `pre_flight_check()` → `bool`
- `CollectorRunner` with parallel execution, failure isolation, and `SecretProvider` abstraction
- Concrete collectors for each source (SonarQube, JIRA, Jenkins, ServiceNow, etc.)
- `rrr-collect --release "X" --status` (pre-flight check) and `--all` (collect all dimensions)
- UI Collect screen driven by `InputContract`-shaped forms

**Why now:**  
Currently, all environment, dependency, security, and performance data must be placed in
`data/*.json` files manually before each assessment run. In any client engagement, this manual
step is the primary friction point — it requires a technically capable person to gather data
from multiple source systems and format it correctly. Without collection automation, RRR cannot
be self-service.

**Value added:**  
- Transforms RRR from a tool that needs manual data prep into a fully automated assessment pipeline
- Enables the "press one button, get a verdict" user experience that clients expect
- Opens the path to event-driven assessment (CI/CD triggers collection + assessment on every deploy)

---

### T-14 · REST API Layer (FastAPI Wrapper)
**Status:** Not started — new ADR required  
**Layer:** New `src/rrr/api/` module · `pyproject.toml` (new `[api]` optional group)

**What it is:**  
Thin FastAPI wrapper over `pipeline.assess()` and `run_and_record()`. Minimum viable endpoints:

```
POST /api/v1/assess          { release, value_stream, tier } → AssessmentOutputModel
GET  /api/v1/releases        ?value_stream=X → list[str]
GET  /api/v1/history/{release} → list[AssessmentOutputModel]
GET  /api/v1/health          → { status, version }
```

**Why now:**  
Without a REST API, RRR can only be triggered from the CLI or the NiceGUI "Run Assessment"
button. CI/CD pipelines cannot trigger assessments via webhook on deploy events. ServiceNow
change management workflows cannot query verdict status. PowerBI or Tableau cannot pull
assessment data for executive dashboards. A REST API is the integration bus that connects RRR
to the enterprise ecosystem.

**Value added:**  
- Enables CI/CD pipeline integration: `POST /api/v1/assess` on every deployment = automated gate
- Enables webhook-triggered assessments from GitHub Actions, Jenkins, ArgoCD
- Enables BI tool integration for executive dashboards (PowerBI, Tableau, Grafana)
- Prerequisite for multi-tenancy (T-20) and the enterprise deployment model

---

### T-15 · Outcome Tracking and Weight Calibration
**Status:** Not started — new design required  
**Layer:** `src/rrr/models/` · `src/rrr/memory/store.py` · `src/rrr/cli.py` · new `scripts/calibrate_weights.py`

**What it is:**  
Three coordinated additions:

**Part A — `ReleaseOutcome` model:**
```python
class ReleaseOutcome(RRRModel):
    release: str
    value_stream: str
    outcome_date: datetime
    outcome_type: OutcomeType  # SMOOTH | INCIDENT_P1 | INCIDENT_P2 | ROLLBACK | PARTIAL_ROLLBACK
    notes: str = ""
```

**Part B — CLI command:**
```
rrr outcome record --release "X" --outcome smooth
rrr outcome list --release "X"
```

**Part C — Calibration script:**
`scripts/calibrate_weights.py` loads all `(AssessmentOutputModel, ReleaseOutcome)` pairs from
SQLite, trains a logistic regression on `(dimension_scores → outcome_type)`, and outputs a
recommended `weights:` YAML block with the empirically derived weights.

**Why now (see also the weights discussion section below):**  
The current weights are expert assumptions. A client programme director will ask: "What evidence
do you have that test readiness should be 27%?" Without calibration data, the answer is
"judgement" — defensible for a prototype, insufficient for an enterprise asset. Outcome tracking
must start from the first deployment so that calibration data exists when it is needed.

**Value added:**  
- The most commercially persuasive improvement possible: "Our weights are calibrated against
  actual production outcomes from your programme"
- Transforms the tool from opinionated to evidence-based
- The calibration script output is an ADR: "We recalibrated weights on 2026-Q4 based on 120
  assessments + 40 release outcomes. New weights: test_readiness: 0.31..."
- Compatible with the deterministic-first invariant — weights are still static config at runtime

---

### T-16 · AHP Weight Justification Documentation
**Status:** Not started — no code required  
**Layer:** `docs/` · `default_config.yaml` (comment update)

**What it is:**  
Produce a `docs/weight-rationale.md` that documents the Analytic Hierarchy Process (AHP)
pairwise comparison that justifies the current default weights. The document states:
- Which expert(s) performed the comparison
- The pairwise comparison matrix for all six weighted dimensions
- The derived priority vector (= the weights)
- The consistency ratio (< 0.10 = acceptable, per Saaty's method)

**Why now:**  
This requires no code changes. AHP is a structured, reproducible method used by McKinsey,
Gartner, and ISO standards for multi-criteria decision making. Running the pairwise comparison
takes half a day. The output is the first honest answer to the "why these weights?" question
that a client will ask. Even if the weights end up the same as today, having an auditable
methodology behind them transforms the conversation from "we guessed" to "we applied a
structured expert elicitation method."

**Value added:**  
- Immediate: defensible weights for the first client presentation
- Medium-term: the AHP matrix is the baseline that T-15 calibration data will eventually
  improve upon — the two approaches are complementary, not competing

---

### T-17 · Per-Assessor Timeout Configuration
**Status:** Not started  
**Layer:** `src/rrr/config/schema.py` · `src/rrr/orchestration/orchestrator.py`

**What it is:**  
Add optional per-assessor timeout overrides to `AssessorsConfig`:
```yaml
assessors:
  test_readiness:
    timeout_seconds: 60   # fast: only reads local brain file
  performance:
    timeout_seconds: 120  # slow: hits Gatling report API
  dependency:
    timeout_seconds: 30
```
`Orchestrator._fan_out()` reads per-assessor timeout from config, falling back to
`assessor_default`.

**Why now:**  
The current uniform 300-second timeout applies to all assessors equally. A `TestReadinessAssessor`
that reads a local JSON file and a `PerformanceAssessor` that calls a Gatling API have vastly
different expected durations. Under the current model, one slow assessor holds up the entire
`wait()` call for up to 5 minutes — even though all other assessors finished in 2 seconds.

**Value added:**  
- Tighter per-assessor timeouts reduce the worst-case assessment duration significantly
- Allows fast local assessors to fail fast rather than waiting for the global timeout
- Required for enterprise deployments where 19 assessors have wildly different latency profiles

---

### T-18 · PDF Output Format
**Status:** Not started  
**Layer:** `src/rrr/output/` · `pyproject.toml` (new `[pdf]` optional group)

**What it is:**  
Add `--format pdf` CLI flag. Implement `PdfRenderer` using `weasyprint` (renders the existing
HTML template to PDF). `weasyprint` is added as an optional dependency (`rrr[pdf]`).

**Why now:**  
Many governance processes (CAB submission, SOX audit, board-level release sign-off) require a
signed PDF with a fixed point-in-time record of the assessment. Exporting to PDF from the
browser is user-error prone (different printers, different layouts). A CLI-generated PDF is
reproducible and consistent.

**Value added:**  
- Closes the governance artefact gap for regulated clients (financial services, government)
- The HTML template already provides 100% of the content — the effort is the renderer only
- A named PDF format in the client proposal is a concrete differentiator vs manual reports

---

## Priority 4 — Strategic (enterprise scale, 2–4 months)

These tasks are required for RRR to operate as a multi-client enterprise platform rather than
a per-engagement tool.

---

### T-19 · Multi-Tenancy (Tenant Context Abstraction)
**Status:** Not started — new ADR required  
**Layer:** New `TenantContext` in `src/rrr/config/` · `src/rrr/memory/store.py` · `src/rrr/ui/app.py`

**What it is:**  
Add a `TenantContext` dataclass:
```python
@dataclass
class TenantContext:
    tenant_id: str
    config: RRRConfig
    store: AbstractAssessmentStore
    brain_dir: Path
```
All pipeline functions accept an optional `TenantContext`. The REST API (T-14) resolves the
tenant from an `X-Tenant-ID` request header. `rrr-ui` shows a tenant switcher in the header.
Each tenant has its own SQLite database, brain directory, and config overlay.

**Why now (strategic):**  
Without multi-tenancy, one RRR instance serves one client. A dedicated instance per client
is operationally feasible for 2–3 clients but does not scale to an Accenture-wide asset (20+
clients). Multi-tenancy is architecturally invasive — the earlier it is designed in, the less
rework is required.

**Value added:**  
- Enables a single Accenture-hosted RRR platform serving multiple client programmes
- Tenant isolation means Client A's data is never accessible by Client B
- Required for the Model C (Enterprise Release Governance Platform) engagement type

---

### T-20 · Assessor Autodiscovery via Entry Points
**Status:** Not started  
**Layer:** `pyproject.toml` · `src/rrr/pipeline.py`

**What it is:**  
Register each assessor class as a Python entry point under the `rrr.assessors` group:
```toml
[project.entry-points."rrr.assessors"]
scope = "rrr.assessors.scope:ScopeAssessor"
test_readiness = "rrr.assessors.test_readiness:TestReadinessAssessor"
# etc.
```
`pipeline.assess()` discovers all registered assessors via `importlib.metadata.entry_points()`.
A third-party package can then add a new assessor without modifying core RRR code.

**Why now (strategic):**  
Currently, adding a new assessor requires modifying `pipeline.py` (the composition root). This
violates the Open-Closed Principle and couples client-specific assessors to the core package.
For a client with a bespoke compliance assessor (e.g., `FCAComplianceAssessor`), entry points
let them ship their assessor as a separate pip package that plugs into RRR without forking it.

**Value added:**  
- Enables client-specific assessors without modifying or forking the core package
- Makes RRR an extensible platform rather than a fixed tool
- The commercial model becomes: Accenture delivers the core + per-client assessor packages

---

### T-21 · Token Budget Enforcement
**Status:** Not started  
**Layer:** `src/rrr/config/schema.py` · `src/rrr/providers/` · `src/rrr/models/assessment.py`

**What it is:**  
Add `max_tokens_per_run: int | null` and `max_cost_usd_per_run: float | null` to `ProviderConfig`.
Track cumulative token usage in `AuditTrail`. If the budget is exceeded mid-run, the remaining
assessors fall back to `RuleBasedProvider` with a MINOR risk factor noting the budget constraint.

**Why now (strategic):**  
When ClaudeProvider or BedrockProvider is used, each assessment run costs money. A single runaway
batch job (e.g., 100 releases triggered simultaneously) can exhaust a client's API quota in
minutes and generate a large unexpected invoice. Token budgeting is standard practice in any
production LLM application.

**Value added:**  
- Prevents unexpected API cost spikes
- Makes the system safe to deploy with automated triggers (CI/CD webhook)
- Token cost tracking in `AuditTrail` enables per-programme cost attribution and chargeback

---

### T-22 · OpenTelemetry Metrics and Tracing
**Status:** Not started — optional dependency  
**Layer:** `src/rrr/orchestration/orchestrator.py` · `src/rrr/providers/` · `pyproject.toml`

**What it is:**  
Add `opentelemetry-sdk` as an optional dependency (`rrr[observability]`). Emit:
- A span per assessor (attributes: `dimension`, `score`, `confidence`, `duration_ms`, `available`)
- A span per provider call (attributes: `provider`, `model`, `tokens_in`, `tokens_out`, `fallback`)
- A counter metric `rrr.assessment.verdict` labelled by verdict and tier
- A histogram `rrr.assessor.duration_ms` labelled by dimension

**Why now (strategic):**  
Operational teams managing RRR in production need visibility into assessment duration trends,
provider fallback rates, and verdict distribution changes. Without metrics, the first signal that
something is wrong is a user complaint.

**Value added:**  
- Enables Prometheus/Grafana dashboards for operational monitoring
- Enables alerts on "provider fallback rate > 10%" and "average assessment duration > 30s"
- Required for any SLA commitment on the `rrr-ui` or REST API

---

### T-23 · RBAC for Dashboard
**Status:** Not started — depends on T-02 (auth) and T-14 (REST API)  
**Layer:** `src/rrr/ui/app.py` · `src/rrr/config/schema.py`

**What it is:**  
Add role-based access control with three roles:
- `viewer` — Overview and Release Detail (read-only)
- `analyst` — History and Trends (full read access)
- `admin` — Ingest screen + config management

Role assignment via config or LDAP group mapping. Each NiceGUI screen checks the current user's
role before rendering.

**Why now (strategic):**  
A delivery programme has multiple stakeholder types with different information needs. A
contractor should not see security posture or compliance risk details for another team's release.
A junior engineer should not be able to trigger the ingest process. RBAC is expected by any
enterprise IT department and is a standard finding in security reviews.

**Value added:**  
- Enables the tool to be safely deployed to a diverse user population (300+ users on a large
  programme) without information exposure risk
- Required for Model C (Enterprise Platform) client engagements

---

## Priority 5 — Longer-Term (future roadmap)

These are strategic investments for when the tool is in active use across multiple client engagements.

---

### T-24 · Outcome-Driven ML Weight Calibration (Full)
**Status:** Depends on T-15 (outcome tracking) having ≥ 50 labelled samples  
**Layer:** New `scripts/ml_calibration.py` · `src/rrr/config/`

**What it is:**  
After T-15 has collected sufficient outcome data (minimum 50 labelled releases — approximately
6 months of programme history), train a gradient-boosted model (XGBoost or LightGBM) on
`(dimension_scores, release_metadata) → outcome_type`. Extract feature importances as the
empirically optimal weight vector. The script outputs a new `weights:` YAML block with a
calibration report (n_samples, feature importances, cross-validation accuracy).

**Value added:**  
- Transforms weight justification from expert judgement to empirical evidence
- Each client engagement produces a programme-specific calibrated weight set
- Feature importances reveal which dimensions are truly predictive of production incidents
  for that client's specific delivery context — this is itself a valuable insight

---

### T-25 · Kubernetes Helm Chart and Docker Compose Packaging
**Status:** Partially started (Dockerfile exists, `docs/enterprise-deployment.md` written)  
**Layer:** New `deploy/helm/` · `deploy/docker-compose.yml` (update)

**What it is:**  
Production-grade deployment packaging:
- Helm chart with configurable replicas, resource limits/requests, PersistentVolumeClaim for
  SQLite, ConfigMap for `default_config.yaml`, Secret for API keys
- `docker-compose.yml` for single-host deployment: rrr-api + rrr-ui + optional Ollama sidecar
- Kubernetes liveness probe pointing at the `/health` endpoint (T-09)
- Kubernetes NetworkPolicy restricting egress to allow-listed hosts (enforcing ADR-0010 at infra level)

**Value added:**  
- Enables one-click deployment on any Kubernetes cluster
- Eliminates the "how do we run this?" question in client engagements
- NetworkPolicy enforces the local-first constraint at the infrastructure level — cannot be
  misconfigured by an application code change

---

### T-26 · PostgreSQL Migration Path
**Status:** Not started — depends on T-08 (export) and T-14 (REST API)  
**Layer:** `src/rrr/memory/store.py` · new `src/rrr/memory/postgres_store.py`

**What it is:**  
Implement `PostgreSQLAssessmentStore(AbstractAssessmentStore)` that uses `asyncpg` or `psycopg3`.
Add `rrr migrate --from sqlite --to postgres --dsn postgres://...` CLI command that uses the
`rrr export` JSONL output to migrate data. Add `backend: postgres` option to `MemoryConfig`.

**Value added:**  
- Required for multi-tenant deployments with > 100,000 assessments
- PostgreSQL supports row-level security (per-tenant data isolation without application code)
- Enables read replicas for the dashboard query load
- The `AbstractAssessmentStore` interface makes this a pure addition — no assessor or
  orchestration code changes required

---

### T-27 · React/Vue Frontend (replacing NiceGUI)
**Status:** Not started — strategic decision, depends on client scale  
**Layer:** New `frontend/` directory · existing `src/rrr/api/` (T-14)

**What it is:**  
A dedicated JavaScript frontend (React + TypeScript recommended) backed by the REST API (T-14).
NiceGUI remains as the admin/development interface. The production dashboard is a static
single-page application served from a CDN.

**Value added:**  
- Supports concurrent access by hundreds of users without event-loop blocking
- Enables mobile-friendly responsive design
- Enables client-specific white-labelling without changing server code
- Required for Model C client engagements at programme scale

---

### T-28 · Source Plugin Registry (Assessor Adapter Package)
**Status:** Not started — depends on T-20 (entry points)  
**Layer:** New separate package `rrr-adapters-jira`, `rrr-adapters-sonarqube`, etc.

**What it is:**  
A family of thin adapter packages that implement `BaseCollector` for common enterprise source
systems. Each adapter is a standalone pip package:
- `rrr-adapters-jira` — JIRA REST API → `ScopeInput`, `EstimationInput`
- `rrr-adapters-sonarqube` — SonarQube API → `TestReadinessInput` (quality metrics)
- `rrr-adapters-servicenow` — CMDB API → `EnvironmentInput`
- `rrr-adapters-snyk` — Snyk API → `SecurityInput`
- `rrr-adapters-dynatrace` — Dynatrace API → `PerformanceInput`

**Value added:**  
- Each adapter represents a reusable integration asset that can be delivered to multiple clients
- Clients with the same toolchain (very common within JIRA/ServiceNow-standardised enterprises)
  get out-of-the-box integration with zero custom development
- The Accenture IP sits in the adapters — the client owns the config, not the code

---

## Summary — Priority Matrix

| Priority | Count | Theme | Estimated effort |
|----------|------:|-------|-----------------|
| 1 — Immediate | 5 | Client safety + data integrity + performance blocker | 2–4 sessions |
| 2 — Short-term | 7 | Production readiness + M6 completion | 6–8 sessions |
| 3 — Medium-term | 6 | Client asset quality + weight credibility | 8–12 sessions |
| 4 — Strategic | 5 | Enterprise scale + multi-client | 12–16 sessions |
| 5 — Longer-term | 4 | Future platform evolution | 20+ sessions |
| **Total** | **27** | | **~50–60 sessions** |

---

## Weight Question — A Separate Path Forward

> See the full analysis in the text response accompanying this file.  
> Short answer: the current fixed-weight model is architecturally correct.  
> The credibility gap is not the mechanism — it is the justification.  
> Three approaches are recommended in parallel, not as alternatives:
>
> 1. **Now (no code):** Run AHP pairwise comparison to produce a defensible methodology (T-16)
> 2. **Short-term (T-15):** Add outcome tracking so calibration data starts accumulating from day one
> 3. **Long-term (T-24):** Run ML calibration once ≥ 50 labelled outcomes are available
>
> The deterministic-first invariant is **preserved** by all three approaches — weights remain
> static config at assessment runtime. The calibration scripts are offline tools that produce
> a recommended config update, not runtime components.
