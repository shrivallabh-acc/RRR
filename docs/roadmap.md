# Roadmap — Release Readiness Results (RRR)

> **Two axes, kept distinct (this used to be conflated — see note below):**
>
> 1. **Execution spine — Milestones `M1`–`M5`.** The single ordered plan of *what gets built when*.
> 2. **Deployment phase — `Phase 1` (local-first, default) → `Phase 2` (external, opt-in).** *Where it
>    runs*, not what it does. This is the **only** meaning of "Phase" in the project, matching
>    CLAUDE.md, the ADRs (ADR-0006, ADR-0010) and the architecture docs. `M1`–`M4` are all Phase 1
>    (fully local); `M5` is the Phase-2 scale-out.
>
> **RRP** (Release Readiness *Prep*) and **RRR** (Release Readiness *Results*) are **capability
> scopes** within the local product — they are *not* deployment phases. Earlier drafts labelled them
> "Phase 1/Phase 2," which collided with the local→external meaning; that labelling has been removed.

## Milestones
| Milestone | Scope | Deployment | Status |
|-----------|-------|------------|--------|
| — | Design: docs, ADRs, diagrams, contracts | Phase 1 | ✅ Complete |
| **M1** | **Foundations** — models, config, tool layer, providers, `BaseAssessor` | Phase 1 | ✅ Complete |
| M2 | **RRP** — readiness prep: checklists, templates, action plans (Markdown) | Phase 1 | ✅ Complete (Jinja2 renderer + verdict_report ✅ 2026-06-19; PlanRenderer + action_plan ✅ 2026-06-19; MockLLMProvider + demo config ✅ 2026-06-20; `--dry-run` ✅ 2026-06-22) |
| M3 | **RRR** — 5 assessors + orchestrator → scored verdict | Phase 1 | ✅ Complete (5 assessors + orchestrator + verdict + property tests) |
| M4 | Persistence, trends, audit trail, evaluation harness, CLI | Phase 1 | ✅ Complete (CLI ✅, SQLite+trends ✅, eval harness ✅, ADR-0014/0015 ✅, LocalLLMProvider ✅, W6 fully ✅ 2026-06-19; Chroma RAG optional 6D vector ✅ 2026-06-19; MockLLMProvider ✅, Docker ✅, LangGraph wrapper ✅ 2026-06-20; scoped CLAUDE.md hierarchy ✅ 2026-06-21) |
| M5 | **Scale-out** — ClaudeProvider, live APIs, NiceGUI dashboard | **Phase 2** | ✅ Complete (ClaudeProvider ✅ 2026-06-25; NiceGUI ✅ 2026-06-26; APIs ✅ 2026-06-28; Trends ✅ 2026-06-28; TOC tagging ✅ 2026-06-28; programme filter ✅ 2026-06-29; Security dim ✅ 2026-06-29; UI redesign ✅ 2026-06-29; hosted persistence interface ✅ 2026-06-30) |
| **M6** | **Assessment Model V2 Extended** — release risk tiers + assessor expansion (12 new assessors, OperationalAssessor split) | **Phase 2** | ✅ Complete (risk tiers ✅ 2026-07-09; OperationalAssessor split ✅ 2026-07-09; 9 gate-only assessors ✅ 2026-07-09) |
| **M7** | **Data Collection Automation** — `rrr-collect` CLI + `rrr-ui` Collect screen + tool adapters | **Phase 1/2** | 🔄 In progress (ADR-0023 Accepted; Phase 1 CLI ✅ 2026-07-09; Phase 2 Collect screen ✅ 2026-07-10; adapters batch 1 ✅ 2026-07-16; batch 2 ⬜) |

## Work breakdown by milestone

### M1 — Foundations (Phase 1)
The typed spine every later milestone builds on.
- [x] Pydantic v2 core models (`DimensionResult`, `ToolInvocationModel`, `EvidenceRecord`, `AssessmentOutputModel`) + LLM I/O models for structured output — **done**; incl. brain/env/dep input contracts; ruff + mypy --strict + smoke tests green against the `g1` fixtures
- [x] `ConfigLoader` + `default_config.yaml` (weights, thresholds, **gates** (ADR-0013), timeouts, memory, retry, assessor-specific) — **done**; deep-merge layering, weights-sum & go>no_go validation, local-first host allow-listing (NFR-8), discriminated file/api sources, `ConfigurationError` with field-pathed list; 11 tests green
- [x] `BaseTool` protocol + `ToolRunner` (timeout + invocation recording) incl. `RKTBrainReader` — **done**; threading timeout, `ToolInvocationModel` per call, `ToolTimeoutError`/`ToolInvocationError` carry the failed record; `RKTBrainReader` selects snapshot/release + exposes planned-SP history for scope-creep; 13 tests green
- [x] `LLMProvider` interface + `RuleBasedProvider` (default, no model) with **structured output + repair-retry guardrail** (`parse_with_repair`) — ADR-0006, ADR-0009 — **done**; `ReasoningRequest` separates instruction from data (injection-safe), rule-based composes prose/remediation from precomputed facts, deterministic; 10 tests green. (`LocalLLMProvider` ✅ built 2026-06-18; `ClaudeProvider` ✅ built 2026-06-25 — Phase 2 opt-in, ADR-0006)
- [x] `BaseAssessor` ABC (`invoke_tool`, `reason` via `LLMProvider`, `calculate_confidence`, `build_evidence`, `reset`) — **done**; template method (subclass implements `_assess`, base orchestrates reasoning→confidence→`DimensionResult`); FR-12 confidence rules; graceful degradation on `ToolError`; provider guardrail fallback caps confidence; 9 tests green

### M2 — RRP: Release Readiness Prep (Phase 1)
Checklists, templates, dry-runs and action plans + the AI-usage log.
- [x] Jinja2 templates for readiness plans & checklists (Markdown export) — `src/rrr/output/` (`MarkdownRenderer` + `verdict_report.md.j2`); `rrr --format markdown` — **done 2026-06-19**; 11 tests.
- [x] **Action-plan generator** (`PlanRenderer` + `action_plan.md.j2`); `rrr --format plan` — CRITICAL/MAJOR/MINOR bucketed checklist, remediation as `- [ ]` checkboxes, unavailable-dimension re-assessment table, re-run instruction footer — **done 2026-06-19**; 9 tests.
- [x] Dry-run / action-plan generation over the foundation models — **`--dry-run` done 2026-06-22**; bypasses SQLite, prints DRY RUN banner
- [x] Start the AI-usage log ([ai-usage.md](ai-usage.md)) — **done**; living log with Framing / Design / Implementation / Testing / Docs stages populated

### M3 — RRR: Release Readiness Results (Phase 1)
The 5 assessor agents (deterministic score + LLM reasoning) + orchestrator → scored verdict.
- [x] Scope assessor (brain story-point completion + LLM scope-creep/ambiguity reasoning) — **done**; completion score + Delivered/Partial/Not classification + scope-creep detection from snapshot history; verified vs g1 (0.958 delivered) & g5 (+30% creep); 5 tests
- [x] Estimation assessor (PV vs Actual variance vs ±10% tolerance + LLM risk narrative) — **done**; variance%/score, over/under/within classification; verified vs g1 (-1%, 0.990) & g5 (-20% over, 0.80); 4 tests
- [x] Environment assessor (file/CSV/API, provisioning status, gap severity) — **done**; avg provisioning score, stability→risk (down=NO_GO/degraded+missing=CONDITIONAL gates), shared `EnvironmentSourceReader` (JSON/CSV/localhost-API, host allow-listed); verified vs g1 (0.950); 8 tests
- [x] Test Readiness assessor (quality / defect-trend / E2E weighted) — **done**; 0.4 quality + 0.3 defect-trend + 0.3 E2E composite, E2E-absent renormalize+confidence-cap (ADR-0012), blocker/critical/sq_below_1 risks; verified vs g1 (0.953) & g2 (0.315); 4 tests. **W5 enhancements done 2026-06-19**: unrun-test penalty (`e2e_score = passed/planned` when `run < planned`) + input-freshness guard (`freshness_max_age_days: 30`, MINOR risk if stale).
- [x] Dependency assessor (completion + integration validation) — **done**; (complete&passed)/total score, blocking/at_risk/on_track per dep, failed→NO_GO/blocking→CONDITIONAL gates; verified vs g1 (1.0) & g3 (0.75 at_risk); 4 tests
- [x] Orchestrator: parallel fan-out/fan-in (ThreadPoolExecutor), weighted scoring, weight redistribution — **done** (LangGraph StateGraph wrapper built 2026-06-20 per ADR-0002 impl note; engine is framework-independent; `orchestration/graph.py` dispatch→collect; `Orchestrator.collect()` public method extracted 2026-06-30 — LangGraph `collect_node` delegates to it, eliminating duplication; ThreadPoolExecutor confirmed as production mechanism, LangGraph as optional tracing layer)
- [x] Verdict mapping (GO / NO-GO / CONDITIONAL / INCOMPLETE) + **veto/cap gates (ADR-0013)** + **LLM verdict rationale & remediation** — **done**; gates via risk-factor severity (CRITICAL→NO_GO/MAJOR→CONDITIONAL), most-restrictive wins; verified end-to-end: g1→GO/96, g2→NO_GO (E2E floor), g5→CONDITIONAL (scope creep). Risk acceptance still pending.
- [x] Hypothesis property tests for scoring invariants + determinism — **done**; score-in-range, weight normalization, verdict determinism, INCOMPLETE-iff-below-minimum, critical-risk→NO_GO, band monotonicity (6 properties)

### M4 — Persistence, Evaluation & CLI (Phase 1)
Make the verdict durable, comparable, evaluated and shippable.
- [x] SQLite persistence + trend comparison (improving / degrading / stable) — **done**; `AssessmentStore` (retry persist, history/latest), `compute_trends` (FR-9), `pipeline.run_and_record` (persist + attach trends); CLI persists each run
- [x] **Chroma** vector memory + **RAG benchmark** over prior releases (ADR-0007) — optional 6D score-vector embedding (scope/estimation/environment/test_readiness/dependency/overall); `AssessmentStore(chroma_path=...)` activates it; `":memory:"` for tests; disabled by default (`chroma_path: null`); `similar_to(k=3)` best-effort; 4 new tests — **done 2026-06-19**
- [x] Click CLI: verdict line, `--verbose` JSON, exit codes 0/1/2/3 — **done**; `rrr --release ... [--config] [--value-stream] [--verbose]`; composition root `pipeline.assess()` wires config→readers→assessors→orchestrator; verified end-to-end (g1→GO/96 exit 0, g2→NO_GO exit 1, unknown→INCOMPLETE exit 3)
- [x] **Evaluation harness**: golden dataset (5 fixtures, all with `ideal.json` oracles) + deterministic metrics (`tests/eval/`: verdict accuracy 100%, macro-F1 1.00, score MAE 0, risk-F1 0.80) — **done 2026-06-17**. **Structural judge + eval report** (`tests/eval/judge.py` + `tests/eval/report.py` + `docs/eval-report.md`, ADR-0008 impl-note) — **done 2026-06-23**; structural score 1.00 on all 5 fixtures; 21 new tests. **Prose quality LLM judge** (`ProseQualityJudge`, `ProseQualityResponse`) — **done 2026-06-26**; uses `ClaudeProvider`; API-key guard for CI; eval report §4 added; FR-28 fully closed; 16 new tests.
- [x] **`LocalLLMProvider`** (Ollama HTTP on 127.0.0.1, stdlib urllib, full guardrail chain, 14 tests) — **done 2026-06-18**; `provider.type: local_llm` now selectable in config
- [x] **W6 structured logging** (run-id per assessment, provider timing per dimension, fallback warnings, `--verbose` enables DEBUG) — **done 2026-06-18**
- [x] **W6 per-assessor hard timeout** (NFR-1) — `_fan_out` uses `wait(timeout=assessor_default)`; timed-out assessors marked unavailable; `shutdown(wait=False)` prevents CLI hang — **done 2026-06-18**; 3 new tests.
- [x] **W6 retry on transient `ToolInvocationError`** — configurable `tools.retry_count` (default 1) + `tools.retry_backoff_s` (default 0.5s) in `ToolRunner`; `BaseAssessor.invoke_tool` retries; `ToolTimeoutError` never retried; `ToolsConfig` Pydantic-validated — **done 2026-06-19**; 3 new tests. **W6 fully closed.**
- [x] Full pytest suite + working end-to-end **demo** (`scripts/run_demo.ps1` — 5 golden fixtures, 5/5 PASS verified) — **done 2026-06-18**
- [x] **`MockLLMProvider`** (fixture-backed, full guardrail chain, `configs/demo.yaml`, `ProviderType.MOCK_LLM`) — offline AI-first demo without Ollama — **done 2026-06-20**
- [x] **LangGraph StateGraph wrapper** (`orchestration/graph.py`, dispatch→collect, ADR-0002 impl note) — **done 2026-06-20**
- [x] **Docker deployment** (`Dockerfile` multi-stage non-root + `docker-compose.yml` optional Ollama sidecar + `.dockerignore`) — **done 2026-06-20**
- [x] **`docs/enterprise-deployment.md`** (90-day engagement cycle, RDE pod fit, client uplift artifacts, K8s topology) — **done 2026-06-20**
- [x] **`rrr-ingest` HTML ingest tool** (`src/rrr/ingest/`: `HTMLExtractor` + `BrainWriter`, separate entry point, ADR-0018) — user drops RKT HTML into a folder; tool converts it to `brain/<value-stream>-history.json`; idempotent upsert on snapshot date — **done 2026-06-22**; 23 tests

### M5 — Scale-Out + Web Dashboard (Phase 2, opt-in)
Everything in `M1`–`M4` is **local-first / offline** (ADR-0010). `M5` is where the tool optionally
**scales outside the machine**, each behind the existing interfaces (no rewrite):
- [x] `ClaudeProvider` (Anthropic Messages API, `claude-sonnet-4-6`) selectable via config — ADR-0006 — **done 2026-06-25**; `pip install rrr[cloud]`; API key via `ANTHROPIC_API_KEY` env var; full guardrail chain; 13 tests; `configs/claude.yaml` reference config
- [x] **NiceGUI dashboard** (`rrr-ui` command, ADR-0020) — release browser + history panel; visual metric bars per release; "Run Assessment" button; verdict card with dimension drill-down; `AssessmentStore.all_recent()`; 20 new tests — **done 2026-06-26**; `pip install rrr[ui]`
- [x] Live external Environment/Dependency/Operational APIs — `ApiSource` config type + HTTP transport fully wired behind `EnvironmentSourceReader`/`DependencySourceReader`/`OperationalSourceReader`; host allow-list enforced at both config-load time and per-invocation; `data/operational.json` stub added; `configs/osm.yaml` updated with commented API example; 19 new tests — **done 2026-06-28**
- [x] Optional hosted persistence / vector store — interface extracted: ``AbstractAssessmentStore`` ABC; ``SQLiteAssessmentStore`` (local impl, backward-compat ``AssessmentStore`` alias); ``RemoteAssessmentStore`` stub wired to ``config.memory.backend: remote``; ``build_store()`` factory in ``pipeline.py``; 3 new interface-contract tests — **done 2026-06-30** (remote backend implementation deferred pending host/auth design)
- [x] Trend visualizations — **Trends tab** in `rrr-ui` with release selector (`AssessmentStore.assessed_releases()`) + score-over-time Apache ECharts line chart with GO/NO_GO threshold lines; `score_history_data()` helper; 9 new tests — **done 2026-06-28**
- [x] **TOC value-stream tagging (ADR-0021)** — `HTMLExtractor._parse_toc()` + `_normalize_name()` (HTML-entity-safe); `toc_value_stream: str | None` on `ReleaseRecord`; `list_toc_value_streams()` on `RKTBrainReader`; Trends tab filter replaced with TOC VS buttons; Releases panel groups by TOC VS (expansion panels); History panel adds VS filter buttons; 14 new tests — **done 2026-06-28**
- [x] **Programme-first selection model (ADR-0022)** — `rrr-ui` auto-scans `brain/` (`list_datasets()`); `--value-stream` removed from `rrr-ui` CLI; programme filter row (stacked above TOC VS filter) added to Releases, History, Trends panels (`list_programmes()`); dataset picker in header when multiple brain files exist; 8 new tests — **done 2026-06-29**
- [x] **Security & Compliance gate-only dimension (ADR-0016 item 2)** — `SecurityComplianceAssessor` (weight=0; contributes only via CRITICAL/MAJOR risk factors → NO_GO/CONDITIONAL verdict cap via GateEngine); `SecurityInput` model; `SecuritySourceReader`; `SastStatus`/`DastStatus` enums; `SecurityAssessorConfig` (`high_cve_threshold=5`); opt-in: dimension only wired when `sources.security` is configured; `data/security.json` stub (clean posture); 23 new tests — **done 2026-06-29**
- [x] **Release Detail panel in `rrr-ui` (ADR-0020)** — `_releases_panel()` rewritten as two-pane `ui.splitter()` master-detail; left: compact release cards + programme filter + TOC VS grouping; right: five-tab detail panel (Overview: metric bars + defects + velocity + earned value + latest verdict; Environment: component table; Dependencies: dependency table; Security: SAST/DAST + CVEs + approvals; Assessments: SQLite history); new data helpers `load_environment()`, `load_dependency()`, `load_security_data()`, `latest_for_release()`; 10 new tests — **done 2026-06-29**
- [x] **`rrr-ui` ground-up UI redesign (ADR-0020)** — `src/rrr/ui/app.py` completely rewritten: persistent left sidebar (140 px) + content-area navigation replacing top-tabs layout. **Overview** home screen: 4-stat health summary (total/NO-GO/CONDITIONAL/unassessed), searchable + filterable + sortable release table (NO_GO→CONDITIONAL→GO urgency sort; unassessed greyed at bottom; click → Release Detail). **Release Detail**: single scrollable page — verdict hero (colour-coded, in-place refresh) → dimension scorecard (score bar + trend ↑↓→) → risk factors → rationale → remediation plan → source metrics → environment → dependencies → security → assessment history with drill-in dialog. Old `_releases_panel`, `_release_detail_panel`, `_detail_overview`, `_detail_assessments` removed. Added: `_nav_item`, `_stat_card`, `_overall_trend`, `_overview_panel`, `_release_detail`, `_VERDICT_HERO_STYLE`, `_VERDICT_SCORE_STYLE`, `_VERDICT_SORT_PRIORITY` — **done 2026-06-29**

### M6 — Assessment Model V2 Extended (Phase 2)

Expands ADR-0016 with release risk tiers, the OperationalAssessor split, and 9 additional
gate-only assessors. All follow the established gate-only pattern (weight=0, ADR-0013
severity → verdict cap, opt-in via `sources.<dim>`). Input contracts defined in
`docs/assessor_inputs.md`; gathering guide in `docs/data-collection-guide.md`.

**Tier system (ADR-0016 items 5–6):**
- [x] **Release Risk Tiers** — `ReleaseRiskTier` enum (`HOTFIX`/`STANDARD`/`MAJOR`) +
  `TierThresholds` Pydantic model (go/no_go/conditional thresholds, required_gate_dims,
  excluded_gate_dims, confidence_floor) + `tiers:` config block in `default_config.yaml` +
  `--tier` CLI flag + orchestrator/verdict tier-aware threshold selection + renderer tier label +
  29 new tests; ADR-0016 items 4–6 impl-note — **done 2026-07-09**
- [x] **Ship-safety vs delivery-performance split** — `ship_safety_score` +
  `delivery_performance_score` in `AssessmentOutputModel`; `split_scores()` in `scoring.py`;
  tier label + sub-scores in Markdown renderer + CLI text output;
  Scope + Estimation = delivery-performance; remaining weighted dims = ship-safety (ADR-0016 item 6) — **done 2026-07-09**

**OperationalAssessor split (ADR-0016 item 7) — done 2026-07-09:**
- [x] **`OperabilityAssessor`** (weighted, 0.07) — deployment pipeline, change management,
  runbooks, on-call, escalation paths; `OperabilityInput`; `data/operability.json` stub;
  `OperabilitySourceReader`; weight rebalance (Operational 0.10 → Operability 0.07 + Observability 0.03);
  golden fixtures updated; `OperationalAssessor` deprecated
- [x] **`ObservabilityAssessor`** (weighted, 0.03) — dashboards, SLO alerts, trace coverage,
  log coverage, runbook-to-alert linkage; `ObservabilityInput`; `data/observability.json` stub;
  `ObservabilitySourceReader`
- [x] **`RollbackAssessor`** (gate-only) — rollback plan, tested procedure, RTO, data rollback;
  `RollbackInput`; `data/rollback.json` stub; `RollbackSourceReader`; CRITICAL: no rollback plan;
  MAJOR: untested or partial

**New gate-only assessors (ADR-0016 items 8–16) — ✅ done 2026-07-09:**
- [x] **`AccessibilityAssessor`** — WCAG gate; `AccessibilityInput` (wcag_target_level,
  critical/major/minor violations, manual_review); `data/accessibility.json` stub;
  CRITICAL: critical violations > 0; MAJOR: major violations > 0; excluded for hotfix tier
- [x] **`ProductionReadinessAssessor`** — go-live checklist gate; `ProductionReadinessInput`
  (capacity, feature flags, checklist, stakeholder sign-offs × 4, comms, support, rollback criteria);
  `data/production_readiness.json` stub; CRITICAL: capacity unconfirmed or checklist incomplete;
  MAJOR: any sign-off missing
- [x] **`RollbackAssessor`** — see OperationalAssessor split above (done 2026-07-09)
- [x] **`DependencyRiskAssessor`** — SCA gate; `DependencyRiskInput` (sca_tool, eol_count,
  critical/high transitive CVEs, malicious_packages, supply_chain_violations, pinned_pct);
  `data/dependency_risk.json` stub; CRITICAL: malicious packages or critical CVEs
- [x] **`FailureModeAssessor`** — resilience gate; `FailureModeInput` (failure_modes_documented,
  critical_paths_pct, circuit_breakers, timeouts, chaos_tests, chaos_pass_rate, graceful_degradation);
  `data/failure_mode.json` stub; CRITICAL: failure modes undocumented or circuit breakers absent
- [x] **`AuditabilityAssessor`** — audit trail gate; `AuditabilityInput` (audit_logging_enabled,
  regulated_events_logged, immutability, retention_days, gdpr_compliant, pii_access_logged, trail_tested);
  `data/auditability.json` stub; CRITICAL: logging disabled or PII not logged
- [x] **`DisasterRecoveryAssessor`** — DR test gate; `DisasterRecoveryInput` (dr_plan_exists,
  last_tested_date, rto/rpo targets vs tested, failover_tested, backup_verified);
  `data/disaster_recovery.json` stub; CRITICAL: plan absent or RTO/RPO targets exceeded
- [x] **`DataReconciliationAssessor`** — migration integrity gate (opt-in);
  `DataReconciliationInput` (migration_applicable, pre/post counts, reconciliation_run, discrepancy);
  `data/data_reconciliation.json` stub; CRITICAL: any discrepancy detected
- [x] **`ArchitectureFitnessAssessor`** — fitness function gate; `ArchitectureFitnessInput`
  (fitness_functions_defined, tests_run/passed/failed, coupling/layering/banned violations, violations list);
  `data/architecture_fitness.json` stub; CRITICAL: layering or banned dependency violations
- [x] **`ArchitectureDriftAssessor`** — drift gate; `ArchitectureDriftInput` (baseline_version,
  adr_compliance_pct, banned_technologies, unapproved_patterns, tech_violations, drift_score);
  `data/architecture_drift.json` stub; CRITICAL: banned technologies or ADR compliance < 80%

> **Each new assessor is a self-contained session:** InputContract model → SourceReader →
> Assessor class → config wiring in `pipeline.py` → `data/<dim>.json` stub → tests (≥10).
> Pattern: follow `SecurityComplianceAssessor` (ADR-0016 item 2) as the reference implementation.

---

### M7 — Data Collection Automation (Phase 1/2)

Introduces `rrr-collect` CLI and `rrr-ui` Collect screen so release teams never hand-edit JSON.
The `CollectorRunner` business logic is shared between CLI and UI (ADR-0023).

**Phase 1 — local, no external deps — ✅ done 2026-07-09:**
- [x] **ADR-0023 accepted** — reviewed and accepted 2026-07-09
- [x] **`src/rrr/collectors/` package** — `BaseCollector` ABC (`dimension`, `collect()` → dict);
  `CollectorResult` dataclass; `CollectorStatus` enum (fresh/stale/missing);
  `CollectorRunner` (`status()` + `run()`); `CollectorRegistry` (14 supplementary dims → `InputContract` class);
  `CollectorConfig` (release, data_dir, skip_optional); no external deps
- [x] **`InteractiveCollector`** — introspects each dimension's `InputContract` Pydantic model
  to generate Click prompts automatically (enum → `Choice`, bool → `confirm`, int/float →
  `prompt` with type, dict/list → skip with advisory); loads existing file as defaults (update mode);
  `--skip-optional` accepts defaults for Optional fields; covers all 14 supplementary dimensions
- [x] **`rrr-collect` CLI entry point** — `pyproject.toml` entry point; `--release`, `--tier`,
  `--dimension`, `--all`, `--status`, `--refresh`, `--skip-optional`, `--data-dir` flags;
  `--status` prints per-dimension traffic-light (exits 0=all fresh, 2=any stale/missing);
  32 tests covering status mode, single dimension, all-dimensions, refresh flag, tier filtering

**Phase 2 — tool adapters (external deps, ADR-0023):**
- [x] **`rrr-ui` Collect screen** ✅ 2026-07-10 — "Collect" nav item in sidebar (admin section);
  status view (FRESH/STALE/MISSING badge per dimension via `collect_status_all()`, Refresh button);
  form view (`_show_form(dim)` introspects `InputContract.model_fields`: Enum→`ui.select`,
  bool→`ui.switch`, int/float→`ui.number`, str→`ui.input`, dict/list→advisory); Save routes through
  `_DictCollector` + `CollectorRunner.run()`; `load_collect_form_data()` enables update mode;
  ADR-0020 impl-note 2026-07-10; ADR-0023 Phase 2 impl-note 2026-07-10; 6 new unit tests
- [x] **Tool adapters batch 1** ✅ 2026-07-16 — `K6Adapter` (file-based, performance), `SnykAdapter`
  (subprocess SCA, security), `SonarQubeAdapter` (HTTP REST, security); `src/rrr/collectors/adapters/`
  subpackage; partial-dict pattern merged by `CollectorRunner`; credentials from env-vars only
  (ADR-0010); 40 offline unit tests (12 k6, 15 snyk, 13 sonarqube); all tests green, mypy clean
- [x] **`docs/data-collection-guide.md`** ✅ 2026-07-16 — comprehensive guide: collection architecture, 14-dimension field reference, `rrr-collect` CLI, `rrr-ui` Collect screen walkthrough, GitHub Actions CI/CD integration examples, Phase 2 tool adapter extension guide (k6 adapter anatomy, conventions, planned adapter roadmap)
- [x] **Codebase cleanup** ✅ 2026-07-26 — `RemoteAssessmentStore` stub removed (all methods raised `NotImplementedError`; replaced by `AbstractAssessmentStore` ABC pattern without a dead stub); `MemoryConfig.backend` narrowed from `Literal["sqlite", "remote"]` to `Literal["sqlite"]`; orphaned `data/operational.json` deleted (dimension renamed to `operability` in ADR-0016 item 7); 1 test removed (`test_remote_store_satisfies_interface_and_raises_on_write`). 766 tests.
- [x] **Comprehensive documentation** ✅ 2026-07-26 — `README.md` completely rewritten (all 4 CLIs with every option, all 21 assessors, full config YAML reference, output formats, release tiers, LLM providers, web dashboard, development workflow); 14 per-folder `README.md` files added (`src/rrr/assessors/`, `collectors/`, `collectors/adapters/`, `providers/`, `config/`, `memory/`, `models/`, `output/`, `ingest/`, `ui/`, `orchestration/`, `tools/`, `tests/`, `data/`, `configs/`).
- [ ] **Tool adapters batch 2** — `axe` + `lighthouse` (accessibility), `grafana` + `datadog`
  (observability + performance), `terraform` (environment), `github_actions` (operability)
- [ ] **Tool adapters batch 3** — `owasp_dep_check` + `snyk_sca` (dependency_risk),
  `gremlin` (failure_mode), `dependency_cruiser` + `import_linter` (architecture_fitness),
  `custom_drift_script` (architecture_drift)

---

## Deployment phases (the "Phase" axis)
| | **Phase 1 — local-first (default, `M1`–`M4`)** | **Phase 2 — external (opt-in, `M5`)** |
|---|---|---|
| Reasoning | `RuleBasedProvider` (no model) or `LocalLLMProvider` (127.0.0.1) | `ClaudeProvider` (Anthropic API) |
| Env/Dep sources | local files / `127.0.0.1` mock APIs | live external APIs |
| Persistence | embedded SQLite + Chroma | optional hosted store |
| UI | CLI + Markdown | + NiceGUI dashboard |

> A fresh checkout runs **fully offline** through `M4`; external services are never required, only
> enabled by explicit config (ADR-0010, ADR-0006). No rewrite to flip Phase 1 → Phase 2.

## Design-review actions (2026-06-16) — backlog
From the senior-architecture review. Each is **approved in principle** (Proposed ADR); implementation
is deferred to the noted milestone. W1–W6 are all built (see table below); Model gap (ADR-0016) remains Proposed / Phase 2.

| Finding | Action | ADR | Target |
|---------|--------|-----|--------|
| W1 — AI-first is currently hollow | Give the LLM a **bounded, measurable** job; `MockLLMProvider` (2026-06-20) now enables offline AI-first demo with full guardrail chain; `LocalLLMProvider` + eval harness satisfy M4 eval gate; full provider adoption (live LLM in loop) remains M5 | ADR-0017 | ✅ MockLLM + LocalLLM (Phase 1 demo); Live LLM → M5 (Phase 2) |
| W2 — gate policy scattered / not configurable | Centralize a **config-driven `GateEngine`** (named, disable-able gates); make the `gates:` block load-bearing | ADR-0014 ✅ Accepted 2026-06-17 | ✅ Done 2026-06-18 — `GateEngine`, named gate signals on `RiskFactor.gate`, 12 new tests |
| W3 — weight redistribution masks missing safety dims | **Required dimensions** — no GO if Test Readiness / Environment unavailable | ADR-0015 ✅ Accepted 2026-06-17 | ✅ Done 2026-06-18 — `required_dimensions` in config + `derive_verdict` cap |
| W4 — confidence ignored by verdict | **Confidence-aware verdict** — cap GO→CONDITIONAL below `confidence_floor` (default 0.70); surface aggregate confidence | ADR-0015 ✅ Accepted 2026-06-17 | ✅ Done 2026-06-18 — confidence floor + `aggregate_confidence` on output + CLI |
| W5 — rate-based scoring ignores coverage/freshness | **Coverage-aware E2E** sub-score (penalize unrun tests) + **input freshness / time-mismatch** guard | — (scoring refinement) | ✅ Done 2026-06-19 — `e2e_score = passed/max(run, planned)`; `freshness_max_age_days: 30` (MINOR risk); config-driven |
| W6 — thin operability | Enforce **per-assessor timeout** (NFR-1), add **run-id + structured logging**, retry on transient failure | — | ✅ run-id + logging done 2026-06-18; ✅ per-assessor timeout done 2026-06-18; ✅ retry on transient `ToolInvocationError` done 2026-06-19 — configurable `tools.retry_count` + `tools.retry_backoff_s`; `ToolTimeoutError` never retried |
| Model gap — only 5 dimensions | **Assessment model v2**: Operational ✅ 2026-06-22; Security ✅ 2026-06-29; Performance ✅ 2026-07-01; **risk tiers + ship-safety split** (items 4–6) + **OperationalAssessor split + 9 gate-only assessors** (items 7–16) = M6 complete 2026-07-09 | ADR-0016 | Items 1–16 ✅ M6 complete |

## Open Questions
- ~~Final `brain/*.json` schema contract with RKT Program Metrics?~~ **Resolved — ADR-0012 / [brain-schema.md](brain-schema.md)** (`<value-stream>-history.json`, read by `RKTBrainReader`).
- ~~Default weight split across the 5 dimensions (must sum to 1.0)?~~ **Resolved — ADR-0011** (Test 0.30 / Scope 0.25 / Environment 0.20 / Dependency 0.15 / Estimation 0.10).
- ~~Who owns the **RKT HTML → brain extract** step?~~ **Resolved 2026-06-22:** `rrr-ingest` CLI built (ADR-0018) — user drops HTML into a folder, `rrr-ingest` converts it to `brain/*.json`.
- Live-API auth model for environment/dependency sources? (Phase 2 / `M5` concern.)
- Benchmark baseline source for the `benchmark` field in the output model?
