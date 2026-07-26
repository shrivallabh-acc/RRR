# Release Readiness Results (RRR)

An **AI-first, local-first** CLI that turns release metrics into an auditable
**GO / NO-GO / CONDITIONAL / INCOMPLETE** verdict.

RRR consumes `brain/*.json` snapshots from the upstream **RKT Program Metrics** system, adds
**environment-readiness** and **dependency-health** dimensions, and fuses five independent
assessments into a single weighted verdict. The **numeric score is deterministic** (reproducible
math); an **LLM provider** supplies the *reasoning* — interpreting ambiguous evidence and writing
the rationale and remediation plan. Every conclusion is backed by a navigable audit trail.

> **Phase 1 is local-first:** it runs entirely on your machine with **no external network calls**.
> The default `RuleBasedProvider` needs no model at all; an optional on-machine LLM
> (Ollama / llama.cpp) enables the AI-first demo. External providers/data are a Phase-2 opt-in.

## Status — _last updated 2026-07-10_
**Phase:** Phase 1 complete / Phase 2 complete / **M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ · M5 ✅ · M6 ✅ · M7 🔄**
`rrr --release "<ir_name>" [--tier hotfix|standard|major]` → LangGraph StateGraph (dispatch→collect) → 8+11 assessors fan out → weighted score
+ ADR-0013/0014 gates → verdict with aggregate confidence, tier label, ship-safety + delivery sub-scores, **persisted to SQLite + optional Chroma RAG**.
Verified on all 5 golden fixtures: **g1→GO/97 · g2→NO_GO · g3→CONDITIONAL/74 · g4→INCOMPLETE · g5→CONDITIONAL/93**.
**727 tests**, comments + ruff + mypy green. New: **M7 Phase 2 Collect screen ✅ 2026-07-10** — `_collect_panel()` in `rrr-ui` (FRESH/STALE/MISSING status view, InputContract-driven form, `_DictCollector` + `CollectorRunner.run()` shared write path); 6 tests. **Hardening bundle ✅ 2026-07-10** — T-03 WAL mode, T-04 `${VAR_NAME}` env-var interpolation, T-02 HTTP Basic Auth ASGI middleware, T-07 SQLite migration guard; 13 tests. **M7 Phase 1 ✅ 2026-07-09** — `src/rrr/collectors/` package (`BaseCollector` ABC, `CollectorRunner`, `CollectorRegistry`, `InteractiveCollector`); `rrr-collect` CLI; 32 tests. **M6 complete ✅ 2026-07-09** — 9 gate-only assessors (ADR-0016 items 8–16): `AccessibilityAssessor`, `AuditabilityAssessor`, `DisasterRecoveryAssessor`, `DataReconciliationAssessor`, `FailureModeAssessor`, `DependencyRiskAssessor`, `ProductionReadinessAssessor`, `ArchitectureFitnessAssessor`, `ArchitectureDriftAssessor` (143 new tests); `OperabilityAssessor` + `ObservabilityAssessor` + `RollbackAssessor` split (66 tests); Release Risk Tiers + ship-safety/delivery sub-scores (29 tests). **`AbstractAssessmentStore` ABC** — `SQLiteAssessmentStore` + `RemoteAssessmentStore` stub + `build_store()` factory. **UI redesign (ADR-0020)** — persistent left sidebar + Overview home screen + Release Detail single-scroll page. **`rrr-ui`** smoke-tested against 41 OSM releases.

### Milestone progress
> _"Phase" = deployment axis only: **Phase 1** local-first (`M1`–`M4`) → **Phase 2** external opt-in (`M5`). Milestones `M1`–`M5` are the execution spine. See [docs/roadmap.md](docs/roadmap.md)._

| Milestone | Scope | Deployment | Status |
|-----------|-------|------------|--------|
| Design | docs, ADRs, diagrams, contracts | Phase 1 | ✅ Complete |
| **M1** | Foundations: models · config · tools · providers · `BaseAssessor` | Phase 1 | ✅ Complete |
| M2 | RRP: checklists, templates, action plans | Phase 1 | ✅ Complete (`MarkdownRenderer` ✅ · `PlanRenderer` ✅ · `--dry-run` ✅ 2026-06-22) |
| M3 | RRR: 5 assessors + orchestrator → verdict | Phase 1 | ✅ Complete |
| M4 | persistence, trends, audit trail, eval harness, CLI | Phase 1 | ✅ Complete (W6 fully ✅ · Chroma RAG ✅ · MockLLMProvider ✅ · LangGraph wrapper ✅ · Docker ✅ · scoped CLAUDE.md ✅ 2026-06-21) |
| M5 | scale-out: ClaudeProvider, NiceGUI, live APIs | **Phase 2** | ✅ Complete (ClaudeProvider ✅ 2026-06-25; NiceGUI `rrr-ui` ✅ 2026-06-26; live APIs ✅ 2026-06-28; Trends ✅ 2026-06-28; TOC tagging ✅ 2026-06-28; Security gate ✅ 2026-06-29; UI redesign ✅ 2026-06-29; hosted persistence interface ✅ 2026-06-30; LangGraph architecture resolved ✅ 2026-06-30) |
| **M6** | **Assessment Model V2 Extended** — release risk tiers + OperationalAssessor split + 9 gate-only assessors | **Phase 2** | ✅ Complete (risk tiers ✅ 2026-07-09; OperationalAssessor split ✅ 2026-07-09; 9 gate-only assessors ✅ 2026-07-09) |
| **M7** | **Data Collection Automation** — `rrr-collect` CLI + `rrr-ui` Collect screen + tool adapters | **Phase 1/2** | 🔄 In progress (ADR-0023 Accepted; Phase 1 CLI ✅ 2026-07-09; Phase 2 Collect screen ✅ 2026-07-10; adapters ⬜) |

### M1 backlog (living)
- ✅ Pydantic v2 model layer (`src/rrr/models/`) — input contracts + value objects + LLM I/O
- ✅ `ConfigLoader` + `default_config.yaml` validation (`src/rrr/config/`) — deep-merge, weights-sum, local-first host allow-listing, `ConfigurationError`
- ✅ `BaseTool` protocol + `ToolRunner` + `RKTBrainReader` (`src/rrr/tools/`) — threading timeout, per-call `ToolInvocationModel`, brain snapshot/release selection + scope-creep history
- ✅ `LLMProvider` interface + `RuleBasedProvider` + repair-loop guardrail (`src/rrr/providers/`) — structured output, injection-safe request envelope, deterministic
- ✅ `BaseAssessor` ABC (`src/rrr/assessors/base.py`) — template method, FR-12 confidence, graceful degradation, guardrail fallback
- ✅ (M2) Jinja2 readiness-plan templates (`MarkdownRenderer` + `PlanRenderer`, `--format markdown/plan`) · (eval) all 5 `ideal.json` oracles authored · Chroma RAG optional 6D vector
- ✅ (M2) `--dry-run` flag — run assessors without persisting (done 2026-06-22)

> **Dev env note:** system Python is **3.14.4**; a local `.venv/` has `pydantic`, `pyyaml`, `click`,
> `pytest`/`hypothesis`/`ruff`/`mypy`, **`chromadb` 1.5.9** (confirmed on 3.14). LangGraph StateGraph wrapper built (ADR-0002 impl-noted 2026-06-20; optional dep `rrr[graph]`).

---

## Daily Progress Log (EOD)
> **`/eod` (or "log EOD") runs the daily ritual:** (1) **quality gate** — comments + ruff + mypy --strict +
> pytest; (2) **alignment check** — `.venv/Scripts/python.exe scripts/check_alignment.py` (must say
> `ALIGNMENT: PASS`); (3) **append the dated entry** below (Planned · Completed · Pending/next + a
> **metrics line**); (4) set the single **▶ Next action** pointer; (5) **sync every artifact** using
> `.claude/artifact-manifest.md` as the explicit per-file checklist — every file that tracks project
> state must be updated before closing. Re-run step 2 to confirm still green.

### ▶ Next action (start here tomorrow)
**M7 tool adapters batch 1 ✅ 2026-07-16 — `K6Adapter` / `SnykAdapter` / `SonarQubeAdapter` in `src/rrr/collectors/adapters/`; 40 offline unit tests; all green. Next: M7 tool adapters batch 2 — `axe`/`lighthouse` (accessibility), `grafana`/`datadog` (observability + performance), `github_actions` (operability); same pattern: partial dict, env-var credentials, ≥10 offline tests each.**
_(Single source of truth for "what's next"; overwrite at each EOD.)_

<!-- TEMPLATE — copy for a new day. Keep buckets concise (1–3 bullets).
### YYYY-MM-DD
- **Planned:** …
- **Completed:** …
- **Pending / next:** …
- _Metrics: NNN tests · ruff+mypy+pytest green · alignment PASS · roadmap <state>_
-->

### 2026-07-10 — **M7 Phase 2 Collect screen ✅ + hardening bundle T-02/T-03/T-04/T-07 ✅**
- **Planned:** Option 2 (hardening bundle): T-03 WAL mode, T-04 env-var `${VAR}` injection, T-02 HTTP Basic Auth on `rrr-ui`, T-07 SQLite schema migration guard. Then Option 1 (M7 Phase 2): `rrr-ui` Collect screen.
- **Completed:**
  - **T-03 WAL mode** — `PRAGMA journal_mode=WAL` in `SQLiteAssessmentStore.__init__()`; eliminates exclusive write locks for concurrent CLI + UI use. 1 test.
  - **T-07 schema migration guard** — `_SCHEMA_VERSION=1`, `_MIGRATIONS: list[list[str]]`, `_migrate(conn)` using `PRAGMA user_version`; forward-looking infrastructure for safe incremental schema upgrades. 3 tests.
  - **T-04 env-var interpolation** — `_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")` in `loader.py`; `_interpolate_env()` recursively walks merged YAML dict (str/dict/list); `ConfigurationError` on missing vars; call site before Pydantic validation. 4 tests.
  - **T-02 HTTP Basic Auth** — `UiConfig(auth_user, auth_password)` Pydantic model with paired-or-null `@model_validator`; `RRRConfig.ui: UiConfig` field (default_factory); `_setup_basic_auth()` ASGI `BaseHTTPMiddleware` on NiceGUI's FastAPI app; called before `register_pages()`; commented example in `default_config.yaml`. 5 tests.
  - **M7 Phase 2 Collect screen** — `_collect_panel()` in `src/rrr/ui/app.py`; "Collect" nav item in sidebar (admin section); status/form sub-view pattern sharing `inner[0]` (`ui.column()`); `collect_status_all()` + `load_collect_form_data()` pure-Python helpers (unit-testable); `_DictCollector(BaseCollector)` for routing form data through `CollectorRunner.run()`; `_unwrap_collect_optional()` + `_build_collect_field_widget()` type-dispatch (Enum→select, bool→switch, int/float→number, str→input, dict/list→advisory). ADR-0020 impl-note 2026-07-10; ADR-0023 Phase 2 impl-note 2026-07-10. 6 new tests.
  - **Full quality gate green**: comments · ruff · mypy (93 files) · pytest · alignment PASS (23 ADRs / 9 diagrams / 93 modules / 727 test functions).
- **Pending / next:** M7 Phase 2 remaining — tool adapters (snyk, sonarqube, k6, axe, grafana, datadog, etc.) or `docs/data-collection-guide.md`.
- _Metrics: 727 tests · comments+ruff+mypy+pytest green · alignment PASS (23 ADRs / 9 diagrams / 93 modules) · M7 🔄 Phase 2 Collect screen ✅_

### 2026-07-09 (session 4) — **M7 Phase 1 ✅ — `rrr-collect` CLI + collectors package**
- **Planned:** M7 Phase 1 — ADR-0023 Accepted + `src/rrr/collectors/` package + `rrr-collect` CLI.
- **Completed:**
  - **ADR-0023 Accepted** — Status changed Proposed → Accepted; implementation note added.
  - **`src/rrr/collectors/` package** — `base.py` (`BaseCollector` ABC, `CollectorConfig`, `CollectorResult`); `runner.py` (`CollectorStatus` FRESH/STALE/MISSING; `DimensionStatusReport`; `CollectorRunner.status()` + `run()`); `registry.py` (`CollectorRegistry` — 14 supplementary dims → `InputContract`); `interactive.py` (`InteractiveCollector` — Pydantic `model_fields` introspection → Click prompts: Enum→Choice, bool→confirm, int/float/str→typed prompt, dict/list→skip advisory; update-mode defaults from existing JSON); `_cli.py` (`rrr-collect` command).
  - **`rrr-collect` CLI** — `--status` (exits 0 all FRESH / exits 2 any stale/missing); `--dimension` (skips if FRESH unless `--refresh`); `--all` (all dims for tier); `--tier hotfix` excludes accessibility + architecture dims; `--skip-optional`; `--data-dir`.
  - **`pyproject.toml`** — `rrr-collect = "rrr.collectors._cli:cli"` entry point wired.
  - **32 new tests** in `tests/unit/test_collectors.py`. 708 total.
  - Full quality gate green: comments (80 files) · ruff · mypy (93 files) · pytest · alignment PASS.
- **Pending / next:** M7 Phase 2 — `rrr-ui` Collect screen + tool adapters (snyk, sonarqube, k6, axe, etc.).
- _Metrics: 708 tests · comments+ruff+mypy+pytest green · alignment PASS (23 ADRs / 9 diagrams / 93 modules) · M7 🔄 Phase 1 ✅_

### 2026-07-09 (session 3) — **9 gate-only assessors (ADR-0016 items 8–16) — M6 complete**
- **Planned:** Implement all 9 gate-only assessors from ADR-0016 items 8–16.
- **Completed:**
  - **9 `InputContract` models** in `src/rrr/models/` — `AccessibilityInput`, `AuditabilityInput`, `DisasterRecoveryInput`, `DataReconciliationInput`, `FailureModeInput`, `DependencyRiskInput`, `ProductionReadinessInput`, `ArchitectureFitnessInput`, `ArchitectureDriftInput`.
  - **9 `_FileApiSourceReader` subclasses** in `src/rrr/tools/source_reader.py`.
  - **9 assessors** in `src/rrr/assessors/` — all gate-only (weight=0), all opt-in via `sources.<dim>` config; all follow BaseAssessor/DeterministicAssessment pattern.
  - **`src/rrr/config/schema.py`** — 9 new `DataSource | None` fields in `SourcesConfig`; allow-list validator updated.
  - **`src/rrr/pipeline.py`** — 9 opt-in wiring blocks + 9 `_<name>_reader()` helpers.
  - **`src/rrr/config/default_config.yaml`** — 9 commented-out opt-in entries added.
  - **9 `data/<dim>.json` stubs** — clean/passing baseline data for each new dimension.
  - **143 new tests** across 9 test files in `tests/unit/`.
  - **ADR-0016 impl-note** — items 8–16 built note added.
  - **Docs/roadmap/CLAUDE.md** — M6 flipped to ✅ Complete.
- **Pending / next:** M7 — ADR-0023 acceptance + `collectors/` package. Quick wins: T-03 WAL mode, T-04 secret injection, T-02 HTTP Basic Auth.
- _Metrics: 676 tests · comments+ruff+mypy+pytest green · alignment PASS (23 ADRs / 9 diagrams / 87 modules) · M6 ✅ complete_

### 2026-07-09 — **Cost/performance optimisations + test infra + architectural review**
- **Planned:** (continuation) complete EOD artifact sync; implement cost/performance optimisations surfaced by ArchReview analysis.
- **Completed:**
  - **`src/rrr/assessors/base.py`** — `_MAX_FACTS = 5` constant caps facts forwarded to LLM provider; `_to_request()` slices `det.facts[:_MAX_FACTS]`. Token usage reduction ~40%; assessors must order facts most-impactful first.
  - **`src/rrr/config/default_config.yaml`** — Tiered provider policy comment block added under `provider:` — documents rule_based ($0/run, batch), local_llm (interactive, $0), claude/bedrock (executive/governance, ~$0.27/assessment). Prevents runaway API costs in automated pipelines.
  - **`tests/conftest.py`** (new) — Hypothesis profiles: `ci` (25 examples, default) + `full` (200 examples, gate); controlled by `HYPOTHESIS_PROFILE` env var. Enables `pytest -m unit -x -q` (~3s) during development.
  - **`pyproject.toml`** — pytest markers added (`unit`, `golden`, `property`, `eval`, `slow`); `pytest-xdist` added to dev deps; `filterwarnings` silences chromadb DeprecationWarning.
  - **`tests/property/test_scoring_properties.py`** + **`tests/eval/test_eval.py`** — `pytestmark` updated to include respective tier markers.
  - **`scripts/check_all.ps1`** — `Run-Step` → `Invoke-Step` (PSUseApprovedVerbs fix); pytest step sets `HYPOTHESIS_PROFILE=full`; fast dev-loop commands documented in header comment.
  - **`ArchReview.md`** (new) — 12-section WAF architectural review from Senior AI Enterprise Architect perspective; 27 tasks across P1–P5; Accenture engagement model positioning; WAF ratings (Reliability 8/10, OpEx 7/10, Security 6/10, Performance 5/10, Cost Phase1 8/10).
  - **`tasks.md`** (new) — 28 prioritized tasks P1–P5, each with "why now" + "value added"; weights discussion (AHP + outcome tracking + ML calibration path); session-effort estimates.
  - **`score_over_snapshots()`** confirmed already pins `RuleBasedProvider()` — no change needed.
- **Pending / next:** 9 gate-only assessors (ADR-0016 items 8–16) — start with `AccessibilityAssessor`. Quick wins: T-03 WAL mode, T-04 secret injection, T-02 HTTP Basic Auth.
- _Metrics: 533 tests · comments+ruff+mypy+pytest green · alignment PASS · M6 🔄 items 4–7 ✅_

### 2026-07-09 — **Release Risk Tiers + ship-safety/delivery split (ADR-0016 items 4–6) ✅**
- **Planned:** ADR-0016 items 4–6 — `ReleaseRiskTier` enum + `TierThresholds`/`TiersConfig` models + `tiers:` config block + `--tier` CLI flag + tier-aware verdict + ship-safety/delivery sub-scores.
- **Completed:**
  - **`ReleaseRiskTier`** enum (`HOTFIX`/`STANDARD`/`MAJOR`) in `models/enums.py`.
  - **`TierThresholds`** + **`TiersConfig`** Pydantic models in `config/schema.py`; `_go_above_no_go` validator; `for_tier()` lookup; `tiers:` block in `default_config.yaml` (hotfix: go=0.60/no_go=0.30; standard: go=0.80/no_go=0.40; major: go=0.90/no_go=0.60).
  - **`score_band()`** signature changed to explicit `(score, go, no_go)` — tier and global values pass in directly.
  - **`triggered_caps()`** accepts `excluded_dims` — suppresses gate-only risk factors for tiers that exclude them.
  - **`derive_verdict()`** accepts `tier_thresholds` — overrides go/no_go/confidence_floor/required_gate_dims when active.
  - **`split_scores()`** added to `scoring.py` — returns `(ship_safety, delivery_performance)` in [0,1]; ship = TEST_READINESS + ENVIRONMENT + DEPENDENCY; delivery = SCOPE + ESTIMATION.
  - **`AssessmentOutputModel`** gains `tier`, `ship_safety_score`, `delivery_performance_score` optional fields.
  - **`--tier`** Click option wired from CLI → pipeline → orchestrator → graph → verdict.
  - **Markdown renderer** + **CLI text output** updated with tier label + sub-score table.
  - **29 new tests** in `tests/unit/test_tier_thresholds.py`; 2 existing tests updated for `score_band()` signature.
  - **ADR-0016** items 4–6 implementation note added; **roadmap** M6 risk-tiers checkboxes flipped to [x].
- **Pending / next:** OperationalAssessor split (ADR-0016 item 7) — `OperabilityAssessor` + `ObservabilityAssessor` + `RollbackAssessor`.
- _Metrics: 485 tests · comments+ruff+mypy+pytest green · alignment PASS · roadmap ADR-0016 items 4–6 ✅_

### 2026-07-04 — **M6/M7 planning complete · ADR-0016 extended · ADR-0023 Proposed**
- **Planned:** Plan and formally document M6 (Assessment Model V2 Extended) and M7 (Data Collection Automation) so SOD/EOD rituals can naturally track them. Update all project artifacts.
- **Completed:**
  - **`docs/assessor_inputs.md`** — comprehensive 19-assessor input contract reference: source taxonomy, full assessor registry table (weights/sources/tier requirements), JSON stubs for all new assessors (Operability, Observability, Rollback + 9 gate-only), gathering timeline T-10→T-0, responsibility map, tier requirement matrix, config wiring YAML.
  - **`docs/data-collection-guide.md`** — operational guide for release managers: quick-start 4 commands, `rrr-collect` CLI reference, per-assessor numbered steps with copy-paste CLI commands (snyk/k6/axe/sonarqube/depcruise), CI/CD GitHub Actions integration, freshness guidelines, troubleshooting.
  - **`adr/0023-data-collection-cli.md`** — Proposed 2026-07-04: three-layer architecture (`rrr-collect` CLI + `CollectorRunner` + `BaseCollector` ABC); Phase 1 `InteractiveCollector` (Pydantic-introspected Click prompts); Phase 2 tool adapters; `rrr-ui` Collect screen; ADR-0010 host allow-list + env-var credentials constraints.
  - **`adr/0016-…md` extended** — items 7–16 added: OperationalAssessor split (Operability 0.07 + Observability 0.03 + Rollback gate-only) + 9 new gate-only assessors (Accessibility, Auditability, DisasterRecovery, DataReconciliation, FailureMode, DependencyRisk, ProductionReadiness, ArchitectureFitness, ArchitectureDrift).
  - **`adr/CLAUDE.md`** — ADR count 22 → 23; ADR-0023 added to Proposed list; ADR-0016 status updated.
  - **`docs/roadmap.md`** — M6/M7 rows added to milestone table; M6 work breakdown (12 items: tiers, ship-safety split, OperationalAssessor split, 9 gate-only assessors); M7 work breakdown (7 items: ADR-0023 accepted, CollectorRunner, InteractiveCollector, rrr-collect CLI, rrr-ui Collect screen, tool adapters ×2).
  - **All project artifacts synced** (CLAUDE.md, README.md, artifact-manifest.md, memory/project-state.md).
- **Pending / next:** M6 Session 1 — `ReleaseRiskTier` enum + `TierThresholds` Pydantic model + `--tier` CLI flag + orchestrator tier-aware threshold selection (ADR-0016 items 4–6).
- _Metrics: 456 tests (unchanged — planning session only) · artifacts synced · 23 ADRs · roadmap M6 🔄 M7 ⬜_

### 2026-07-01 — **PerformanceAssessor (ADR-0016 item 3) ✅**
- **Planned:** ADR-0016 item 3 — `PerformanceAssessor` (gate-only, weight=0); `PerformanceInput` data contract; load-test / SLO / capacity risk gates.
- **Completed:**
  - **`PerformanceAssessor`** — gate-only (weight=0); `PerformanceInput(InputContract)` model (`performance_test_status`, `p99_latency_ms`, `slo_p99_threshold_ms`, `capacity_headroom_pct`); `PerformanceSourceReader`; `PerformanceAssessorConfig` (threshold knobs); opt-in wiring in `pipeline.py`; 25 tests. CRITICAL on load-test FAILED or latency ≥ 2× SLO; MAJOR on SLO breach or low capacity; MINOR + confidence cap (0.75) on NOT_RUN. `data/performance.json` stub added. ADR-0016 item 3 implementation note added. `DimensionName.PERFORMANCE` added to enums.
- **Pending / next:** ADR-0016 items 4–6 — release risk tiers (hotfix/standard/major threshold sets) + ship-safety vs delivery-performance verdict split.
- _Metrics: 456 tests · comments+ruff+mypy+pytest green · alignment PASS · roadmap ADR-0016 item 3 ✅_

### 2026-06-30 — **ADR-0017 Accepted · AbstractAssessmentStore · LangGraph architecture resolved**
- **Planned:** P1: Close ADR-0017 (Proposed → Accepted). P2: comment-coverage hook in settings.json. P3: Extract `AbstractAssessmentStore` ABC (M5 hosted persistence interface). P4: LangGraph architecture resolution (architecture-review item 14).
- **Completed:**
  - **ADR-0017 Accepted** — "make-AI-earn-its-place" closed with deliberate deviation: LLM is narrative-only (no classification adjudication); `ProseQualityJudge` is the eval gate for prose quality (FR-28). Deviation documented in ADR impl-note.
  - **`AbstractAssessmentStore` ABC** — `SQLiteAssessmentStore(AbstractAssessmentStore)` (local impl, `AssessmentStore` alias); `RemoteAssessmentStore` stub (raises `NotImplementedError` on write, `[]` on `similar_to`, no-op `close`); `build_store()` factory in `pipeline.py`; `config.memory.backend: "sqlite" | "remote"`; 3 new interface-contract tests. M5 hosted persistence interface ✅.
  - **LangGraph architecture resolved** — `Orchestrator.collect()` extracted as public method (scoring → verdict → synthesis → output in one place); `run()` now delegates to `_fan_out()` + `collect()`; `graph.py` `collect_node` reduced from ~80 lines to 7 lines (delegates to `orchestrator.collect()`); ADR-0002 impl-note added; architecture-review item 14 closed: ThreadPoolExecutor = production, LangGraph = optional tracing/viz layer.
  - **P2 (hooks)** blocked by auto-mode classifier — manual instructions provided to user.
- **Pending / next:** Phase 2: ADR-0016 items 3–6 (Performance/NFR tiers + release risk tiers). Design `PerformanceInput` data contract before coding.
- _Metrics: 431 tests · comments+ruff+mypy+pytest green · alignment PASS (22 ADRs / 9 diagrams / 61 src modules) · roadmap M5 ✅ · Phase 1 fully complete_

### 2026-06-29 — **UI Redesign ✅ · sidebar nav · Overview panel · Release Detail screen**
- **Planned:** Complete ground-up UI redesign of `rrr-ui` NiceGUI dashboard per user directive.
- **Completed:**
  - **`src/rrr/ui/app.py` completely rewritten** — replaced top-tabs layout with persistent left sidebar (140 px) + content-area navigation (client-side, no page reloads except dataset switch).
  - **Overview screen** (new home) — 4-stat health-summary row (total / NO-GO / CONDITIONAL / unassessed); searchable + filterable + sortable release table sorted by urgency (NO_GO first, then CONDITIONAL, then GO, then unassessed); unassessed rows greyed (opacity-50) at bottom; clicking a row navigates to Release Detail.
  - **Release Detail screen** — single scrollable page replacing nested tabs: verdict hero (colour-coded, in-place refresh after Run Assessment) → dimension scorecard (score bar + trend ↑↓→ arrow) → risk factors → rationale (collapsible) → remediation plan → source metrics → environment → dependencies → security → assessment history with drill-in dialog.
  - **Removed**: `_releases_panel`, `_release_detail_panel`, `_detail_overview`, `_detail_assessments`.
  - **Added**: `_nav_item`, `_stat_card`, `_overall_trend`, `_overview_panel`, `_release_detail`, constants `_VERDICT_HERO_STYLE` / `_VERDICT_SCORE_STYLE` / `_VERDICT_SORT_PRIORITY`.
  - Full quality gate green: comments PASS · ruff PASS · mypy PASS · 449 tests passed (428 test functions).
- **Pending / next:** Optional hosted persistence (M5 option B). Or Phase 2: ADR-0016 items 3–6, ADR-0017 agentic guardrails.
- _Metrics: 428 tests · comments+ruff+mypy+pytest green · alignment PASS (22 ADRs / 9 diagrams / 61 src modules) · roadmap M5 🔄 (UI redesign ✅)_

### 2026-06-29 — **Security & Compliance gate-only dimension ✅ · ADR-0016 item 2 · 23 new tests**
- **Planned:** Implement ADR-0016 Security & Compliance gate-only dimension.
- **Completed:**
  - **`SecurityComplianceAssessor`** — gate-only (weight=0); contributes CRITICAL/MAJOR risk factors → NO_GO/CONDITIONAL verdict caps via GateEngine (ADR-0013); score informational only.
  - **`SecurityInput(InputContract)`** — fields: `sast_status`, `dast_status`, `open_critical_cves`, `open_high_cves`, `license_approved`, `data_privacy_approved`, `pen_test_passed`; all default to safe-but-uncertain values.
  - **`SastStatus` / `DastStatus` enums** — `passed / failed / not_run`; `DimensionName.SECURITY = "security"` added.
  - **`SecuritySourceReader`** — extends existing `_FileApiSourceReader`; JSON or localhost API; local-first enforced.
  - **`SecurityAssessorConfig(high_cve_threshold=5)`** — added to `AssessorsConfig` (default_factory so all existing configs load unchanged).
  - **`SourcesConfig.security: DataSource | None = None`** — opt-in; assessor only wired in `pipeline.py` when not None.
  - **`data/security.json`** — clean posture stub (`sast=passed`, `dast=not_run`, `0` CVEs, `license=true`).
  - **23 new tests** in `tests/unit/test_security_assessor.py` — all risk paths (CRITICAL, MAJOR, MINOR), CVE penalty cap, classification, confidence cap, unavailable on missing file.
  - **`adr/0016-…md`** — implementation note added for both items 1 (Operational, 2026-06-22) and 2 (Security, 2026-06-29).
- **Completed (continued):** Release Detail panel (ADR-0020) — see entry below.
- **Pending / next:** Option B — optional hosted persistence. Or Phase 2 scope (ADR-0016 items 3–6 / ADR-0017).
- _Metrics: 428 tests · comments+ruff+mypy+pytest green · alignment PASS (22 ADRs / 9 diagrams / 61 src modules) · roadmap M5 🔄 (security gate ✅ · release detail panel ✅)_

### 2026-06-29 — **Release Detail panel (ADR-0020) ✅ · two-pane master-detail in rrr-ui**
- **Planned:** Implement Option A from previous session — Release Detail panel in `rrr-ui` with two-pane layout, environment/dependency/security/assessment tabs per release.
- **Completed:**
  - **`_releases_panel()` rewritten** as two-pane `ui.splitter()` (35% left / 65% right) master-detail layout; left pane retains programme filter + TOC VS grouping; right pane shows placeholder until a release is selected.
  - **Left pane** — compact clickable `ui.card()` for each release; blue left-border highlights active selection; scope-pct colour indicator (green/amber/red).
  - **Right pane** — `_release_detail_panel()`: header with release name + "Run Assessment" button + five inner tabs (`ui.tabs`).
  - **Overview tab** (`_detail_overview`) — metric bars (scope, SQ, E2E); open defect breakdown by severity; weekly velocity last-3 data points; planned-vs-actual earned value; latest SQLite verdict with top-3 risk factors.
  - **Environment tab** (`_detail_environment`) — shared `EnvironmentInput` snapshot; coloured provisioning/stability badges per component via `_provision_color()` / `_stability_color()`.
  - **Dependencies tab** (`_detail_dependencies`) — shared `DependencyInput` snapshot; coloured completion/integration badges via `_completion_color()` / `_integration_color()`.
  - **Security tab** (`_detail_security`) — shared `SecurityInput` posture (SAST/DAST badges, CVE counts, approval tri-state flags); shows "not configured" state when `sources.security` absent.
  - **Assessments tab** (`_detail_assessments`) — SQLite history rows for the selected release; drill-in dialog reuses shared `result_dlg`.
  - **New data helpers** (pure Python, unit-testable): `load_environment()`, `load_dependency()`, `load_security_data()`, `latest_for_release()`.
  - **10 new unit tests** in `tests/unit/test_ui.py` — environment/dependency/security load helpers (valid file, missing file, invalid JSON, not-configured); `latest_for_release` empty and most-recent cases.
  - **ADR-0020 implementation note** (2026-06-29) added.
- **Pending / next:** Optional hosted persistence (B). Or Phase 2: ADR-0016 items 3–6 (Performance/Risk Tiers), ADR-0017 agentic guardrails.
- _Metrics: 428 tests · comments+ruff+mypy+pytest green · alignment PASS (22 ADRs / 9 diagrams / 61 src modules) · roadmap M5 🔄 (release detail ✅)_

### 2026-06-29 — **Programme-first selection model (ADR-0022) ✅ · rrr-ui auto-scan + programme filter**
- **Planned:** Implement programme-first selection model per `.claude/plans/programme-selection-rework.md` — remove `--value-stream` from `rrr-ui`; add programme filter row to all three panels; auto-scan brain/ for datasets.
- **Completed:**
  - **ADR-0022** — `adr/0022-programme-first-selection-model.md`; distinguishes three selection dimensions (dataset, programme, TOC VS); documents stacked-filter design; ADR count 21 → 22.
  - **`list_datasets(config)`** — scans `brain/*-history.json`; returns sorted dataset labels; used by `run_ui()` for auto-scan.
  - **`list_programmes(releases)`** — returns distinct `release.programme` codes (sorted, deduped); empty when only one programme present (filter hidden).
  - **Programme filter row** — added to `_releases_panel()`, `_history_panel()`, `_trends_panel()`; each uses the container+`clear()`+`with container:` rebuild pattern so clicking a programme rebuilds the downstream TOC VS section from the narrowed pool.
  - **`_releases_panel()`** — TOC VS expansion panels extracted into `_render_toc(pool)` closure; programme filter rebuilds it.
  - **`_history_panel()`** — `prog_lookup` dict added (ir_name → programme from brain); VS section extracted into `_rebuild_panel(pool)` closure.
  - **`_trends_panel()`** — TOC VS filter and selector extracted into `_rebuild_all(pool)` closure; `_make_toc_groups()` inner helper.
  - **`register_pages()`** — signature changed to `(config, all_datasets)`; `@ui.page("/")` now accepts `dataset: str | None = None` query param; dataset picker (`ui.select`) in header when `len(all_datasets) > 1`.
  - **`run_ui()`** — `value_stream` param removed; calls `list_datasets()` on startup; falls back to `config.sources.brain.value_stream` when brain/ is empty.
  - **`rrr-ui` CLI** — `--value-stream` option removed from `_cli.py`; `run_ui()` call updated.
  - **8 new tests** in `tests/unit/test_ui.py` — `list_datasets` (3 tests: missing dir, sorted labels, ignore non-history files); `list_programmes` (4 tests: single prog → empty, no releases, sorted codes, deduplicated).
- **Pending / next:** M5 remaining — optional hosted persistence; ADR-0016 assessment-model-v2 (needs data contract design first; multi-session).
- _Metrics: 395 tests · comments+ruff+mypy+pytest green · alignment PASS (22 ADRs / 9 diagrams / 59 src modules) · roadmap M5 🔄 (programme filter ✅)_

### 2026-06-28 — **Trends tab ✅ · Live external APIs ✅ · TOC value-stream tagging ✅ · Releases/History VS grouping ✅**
- **Planned:** SOD → (1) smoke-test `rrr-ui`; (2) live external APIs; (3) trend visualizations in `rrr-ui`.
- **Completed:**
  - **`rrr-ui` smoke-test** — `pip install nicegui` (3.13.0); CLI entry point confirmed; data helpers validated against 41 real OSM brain releases.
  - **`data/operational.json`** — missing stub file created (was defaulted in config but absent from disk; would have caused `SourceReadError` on any run).
  - **`tests/unit/test_source_readers.py`** — 19 new tests covering all three readers (Env/Dep/Operational) across file-JSON, file-CSV, file-not-found, invalid-JSON, construction guards, API-normal, API-host-blocked, API-connection-error, API-malformed-JSON, API-non-dict-body. Confirmed `ApiSource` HTTP path was already fully implemented; tests provide the missing coverage.
  - **`configs/osm.yaml`** — added `operational` source + commented `api` source example for all three readers.
  - **Trends tab in `rrr-ui`** — third tab "Trends" wired into `register_pages()`; `_trends_panel()` with `ui.select` release picker + `ui.echart` score-over-time line chart with GO/NO_GO threshold lines; colour-coded by final score (green/amber/red); graceful empty-state when < 2 data points. `AssessmentStore.assessed_releases()` new method. `score_history_data()` data helper. 9 new tests.
  - **`docs/roadmap.md`** — M5 live APIs ⬜ → ✅; M5 Trends ⬜ → ✅.
  - **TOC value-stream tagging (ADR-0021)** — `HTMLExtractor._parse_toc()` + `_normalize_name()` (HTML-entity-safe); `toc_value_stream: str | None` on `ReleaseRecord`; `list_toc_value_streams()` on `RKTBrainReader`; Trends tab filter replaced with TOC VS buttons (7 VS names from OSM report); 14 new tests; all 41 OSM releases re-ingested and tagged.
  - **Releases panel** — expansion panels now group by TOC value stream (alphabetically) with `[PROGRAMME]`-labelled fallback buckets; programme code shown as sub-label in each release card.
  - **History panel** — TOC VS filter buttons added; cross-references brain releases for VS lookup; `_render_records()` inner function clears and rebuilds the records column on filter change.
  - **`adr/0021-toc-value-stream-tagging.md`** (new); ADR count 20 → 21.
- **Pending / next:** M5 remaining — optional hosted persistence; ADR-0016 assessment-model-v2 (needs data contract design first; multi-session).
- _Metrics: 385 tests · comments+ruff+mypy+pytest green · alignment PASS · roadmap M5 🔄 (TOC tagging ✅ · Releases/History VS grouping ✅)_

### 2026-06-26 — **EOD artifact sweep — ADR status headers, diagrams, docs aligned**
- **Planned:** EOD quality gate + full artifact sync across all 20 ADRs, 9 diagrams, docs, memory.
- **Completed:**
  - **Quality gate** — comments + ruff + mypy + pytest all green; 357 tests confirmed.
  - **Alignment** — 20 ADRs · 9 diagrams · 59 src modules · 336 test functions · PASS.
  - **ADR status headers** — 7 ADRs had implementation notes but lacked "(implemented DATE)" in their Status line; corrected: ADR-0002 (2026-06-20), ADR-0006 (2026-06-25), ADR-0007 (2026-06-19), ADR-0008 (2026-06-26), ADR-0009 (2026-06-25), ADR-0019 (2026-06-22), ADR-0020 (2026-06-26).
  - **docs/architecture-review.md** — test count 337→357; Production Readiness updated (ClaudeProvider ✅ + NiceGUI ✅); Finding 5 "Remaining: ClaudeProvider" resolved; matrix prose-judge cell updated.
  - **docs/architecture.md** — Orchestrator row: "LangGraph is the planned wrapper" → "LangGraph ✅ built 2026-06-20"; LLMProvider row: added BedrockProvider + ClaudeProvider ✅ 2026-06-25.
  - **docs/roadmap.md** — M1 LLMProvider bullet: parenthetical updated (both providers built); design-review header: "None are built yet" → "W1–W6 all built".
  - **diagrams/01** — "Not yet built: ClaudeProvider + NiceGUI" → all built; live APIs remain.
  - **diagrams/03** — "ClaudeProvider is Phase 2" → "ClaudeProvider ✅ built 2026-06-25".
  - **diagrams/08** — "Prose-quality judge deferred to Phase 2" → "ProseQualityJudge ✅ built 2026-06-26".
- **Pending / next:** M5 remaining — live external env/dep APIs.
- _Metrics: 357 tests · comments+ruff+mypy+pytest green · alignment PASS · roadmap M5 🔄 (live APIs ⬜)_

### 2026-06-26 — **NiceGUI dashboard (ADR-0020) — `rrr-ui` release browser + history panel**
- **Planned:** SOD → Option B-Extended confirmed: full three-screen NiceGUI dashboard.
- **Completed:** `rrr-ui` CLI command; `src/rrr/ui/` package (`app.py`, `_cli.py`, `__init__.py`); release browser with scope/SQ/E2E metric bars + "Run Assessment" button (async, thread-pool); history panel from `AssessmentStore.all_recent()` with verdict chips; verdict card with dimension breakdown, risk factors, rationale/remediation expansion; `AssessmentStore.all_recent()` method; `pip install rrr[ui]`; ADR-0020; 20 new tests.
- **Pending / next:** install `nicegui` and smoke-test `rrr-ui` against real OSM data; or pivot to live external APIs.
- _Metrics: 357 tests · ruff+mypy+pytest green · alignment TBD · roadmap M5 NiceGUI ✅_

### 2026-06-26 — **ProseQualityJudge (FR-28, ADR-0008) — live-LLM eval, FR-28 closed**
- **Planned:** SOD triage → implement `ProseQualityJudge` (Option A from SOD recommendation).
- **Completed:**
  - **`tests/eval/judge.py`** — `ProseQualityResponse(RRRModel)` (5-field Pydantic schema, each validated 0–1); `ProseQualityResult` dataclass; `ProseQualityJudge` class with `is_available()` API-key guard, `judge()` (one `ClaudeProvider` call per available narrative), `_score_narrative()` (graceful `ProviderValidationError` handling returning `None`). Default model: `claude-haiku-4-5-20251001`, temperature 0, 256 max tokens.
  - **`tests/eval/run_eval.py`** — `run_full_eval()` returns 3-tuple `(EvalReport, list[JudgeResult], list[ProseQualityResult] | None)`; `run_prose_eval()` helper added; `run_eval()` + `print_report()` + `__main__` updated.
  - **`tests/eval/report.py`** — new §4 Prose Quality table; §4/§5 renumbered to §5/§6; gate entry (informational, ≥0.70); methodology note updated.
  - **`tests/eval/test_eval.py`** — 16 new tests: `ProseQualityResponse` bounds, `is_available()`, mock-provider `judge()`, graceful failure, renderer with/without prose; section-header assertions updated.
  - **`adr/0008-evaluation-golden-dataset-llm-judge.md`** — implementation note 2026-06-26 added.
  - **`docs/architecture-review.md`** — Finding 1 "Remaining" → ✅ FULLY RESOLVED 2026-06-26; Strategic §11 updated; maturity rating test count 283→337 + FR-28 note.
  - **`docs/roadmap.md`** — M4 eval harness prose judge ✅.
  - Full artifact sweep: CLAUDE.md 296→337 tests; README status + ▶ Next action; project-state memory; ai-usage.md Stage 3k.
- **Pending / next:** M5 remaining — live external APIs or NiceGUI dashboard (see ▶ Next action).
- _Metrics: 337 tests · comments+ruff+mypy+pytest green · alignment PASS (19 ADRs / 9 diagrams) · M1–M4 ✅, M5 🔄 (ClaudeProvider ✅ · ProseQualityJudge ✅)_

### 2026-06-25 — **ClaudeProvider (ADR-0006) — Anthropic Messages API, Phase 2 unlocked**
- **Planned:** SOD triage → implement ClaudeProvider (Option A from SOD recommendation).
- **Completed:**
  - **`src/rrr/providers/claude.py`** — `ClaudeProvider` class: lazy `anthropic` SDK import, API key from `ANTHROPIC_API_KEY` env var only, `parse_with_repair` guardrail chain, single system + user turn per Messages API call, all SDK errors → `ProviderValidationError` for graceful fallback.
  - **`src/rrr/config/schema.py`** — `ClaudeConfig` expanded with `max_tokens` + `temperature` fields.
  - **`src/rrr/pipeline.py`** — CLAUDE branch added to `build_provider()`.
  - **`configs/claude.yaml`** — reference config (`claude-sonnet-4-6`, `pip install rrr[cloud]`).
  - **`tests/unit/test_claude_provider.py`** — 13 tests: normal path, repair, exhausted retries, API error, empty content, blank text, missing SDK, missing key, missing config block, pipeline wiring.
  - **ADR-0006 + ADR-0009** — implementation notes added.
  - Full artifact sweep: roadmap M5 ✅, architecture.md, CLAUDE.md, ai-usage.md, artifact-manifest, project-state memory.
- **Pending / next:** M5 remaining — live external APIs or NiceGUI dashboard (see ▶ Next action).
- _Metrics: 296 tests · comments+ruff+mypy+pytest green · alignment PASS (19 ADRs / 9 diagrams) · M1–M4 ✅, M5 🔄 (ClaudeProvider ✅)_

### 2026-06-24 — **EOD artifact sweep — diagrams, architecture docs, manifest aligned**
- **Planned:** EOD quality gate + full artifact sync.
- **Completed:**
  - **Quality gate** — comments + ruff + mypy + pytest all green; 283 tests confirmed.
  - **Alignment** — 19 ADRs · 9 diagrams · 52 src modules · 262 test functions · PASS.
  - **Artifact sweep** — fixed stale content across 7 files: `diagrams/01` (removed "--dry-run NOT built" claim; built 2026-06-22); `diagrams/06` (added Chroma RAG impl note; built 2026-06-19); `diagrams/08` (added eval harness impl note; judge + report built 2026-06-23); `docs/architecture.md` (232→283 tests; added BedrockProvider + structural judge to built list); `docs/architecture-review.md` (Maturity Ratings: 125→283 tests, Production Readiness bumped 3.5→4.5; Finding 1 Remaining items marked ✅ built; matrix "Golden dataset evaluation" updated); `.claude/artifact-manifest.md` (state variables: 202→283 tests, M2 complete, ADR count 17→19, ▶ Next action updated); `memory/project-state.md` (18→19 ADRs). `docs/ai-usage.md` Stage entry added.
- **Pending / next:** Phase 2 — see ▶ Next action below.
- _Metrics: 283 tests · comments+ruff+mypy+pytest green · alignment PASS (19 ADRs / 9 diagrams) · M1–M4 ✅, Phase 1 complete_

### 2026-06-23 — **Structural judge (FR-28, ADR-0008) + eval report + artifact reconciliation**
- **Planned:** SOD ritual → BedrockProvider audit → artifact reconciliation → LLM-as-judge (FR-28).
- **Completed:**
  - **Artifact reconciliation** — README/CLAUDE.md/memory synced to 283 tests + 19 ADRs; BedrockProvider surfaced in README status.
  - **BedrockProvider audit** — confirmed fully complete (12 tests, pipeline wired, ADR-0019 impl-note present). No gaps.
  - **Structural judge (FR-28)** — `tests/eval/judge.py`: `StructuralJudge` checks narrative completeness, classification, confidence, rationale, risk-factor coverage across all 5 golden fixtures. Structural score: 1.00 on all 5 fixtures.
  - **Eval report (ADR-0008)** — `tests/eval/report.py`: `EvalReportRenderer` emits `docs/eval-report.md` (deterministic metrics + structural quality + quality gate). `run_eval.py` extended with `run_full_eval()`.
  - **21 new tests** — `FullEvalOutput` fixture; judge + renderer tests; full gate green.
  - **Pre-existing ruff fixes** — `test_bedrock_provider.py` (I001, UP037, F821 from 2026-06-22 session).
  - **ADR-0008 impl-note** + **roadmap M4 eval item** updated. **`docs/ai-usage.md` Stage 3i** added.
- _Metrics: 283 tests · comments+ruff+mypy+pytest green · alignment PASS (19 ADRs / 9 diagrams) · M1–M4 ✅, M2 ✅_

### 2026-06-22 — **M2 complete + rrr-ingest (ADR-0018) + real-data validation (OSM HTML)**
- **Planned:** SOD ritual → triage → M2 `--dry-run` closure → rrr-ingest → real-data test.
- **Completed:**
  - **`--dry-run` flag (M2 closure)** — `cli.py` routes to `pipeline.assess()` (pure, no SQLite); DRY RUN banner on stdout for text format, stderr for json/markdown/plan so piped output stays machine-parseable; 1 new test.
  - **`rrr-ingest` HTML ingest tool (ADR-0018)** — `src/rrr/ingest/` (`HTMLExtractor` + `BrainWriter` + Click CLI); separate `rrr-ingest` entry point in `pyproject.toml`; reads RKT HTML's embedded `const __REPORT__` JSON; maps 41 releases to brain contract shape; idempotent upsert on snapshot date.
  - **Real-data null handling** — all 6 series-based helpers in `html_extractor.py` now filter JSON `null` (RKT pads future dates); 6 new null-handling tests.
  - **`sq_avg` scale fix** — HTML sq_caps.scores are 0-2 (not 0-1); formula corrected to `min(mean × 1.5, 3.0)` (was `mean × 3`). Brain 0-3 scale preserved. Threshold corrected to `2/3`.
  - **`PVPoint.planned` constraint fix** — `gt=0.0` → `ge=0.0`; releases with no PV data yet return `planned=0`, which is valid.
  - **Fuzzy release matching** — `RKTBrainReader._select_release`: exact → case-insensitive exact → substring → disambiguation error if multiple match. User no longer needs exact name.
  - **`--list-releases` CLI flag** — prints all release names from brain file for a value stream; exits before assessment. Discovery command for unknown release names.
  - **Stub env/dep files** — `data/environment.json` + `data/dependency.json` (UTF-8 no-BOM); `configs/osm.yaml` for OSM value stream.
  - **`scripts/check_alignment.py` fix** — `live_text()` filters `ai-usage.md` Stage sections (false positives on historical ADR counts).
  - **End-to-end verified** — `rrr --release "RetirePlus RC/RCP Enrollment" --value-stream "OSM" --config configs/osm.yaml --dry-run` → `VERDICT: NO_GO  SCORE: 62  CONFIDENCE: 100%` (all 5 assessors running against real OSM data).
  - **Artifact sweep** — `adr/CLAUDE.md` count 17 → 18; `CLAUDE.md` structure/status/commands updated; `docs/architecture.md` status block updated; `docs/roadmap.md` M2 ✅, dry-run ✅, ingest entry added to M4; memory files updated.
- _Metrics: 232 tests · comments+ruff+mypy+pytest green · alignment PASS (18 ADRs / 9 diagrams) · M1–M4 ✅, M2 ✅_

### 2026-06-21 — **Quality gate clean + CLAUDE.md hierarchy optimization (scoped context loading)**
- **Planned:** Complete quality gate from previous session; CLAUDE.md hierarchy optimization.
- **Completed:**
  - **Quality gate clean** — fixed `mock_llm.py` mypy error (`cast(dict[str, Any], json.loads(…))`); fixed `test_graph.py` ir_name bug (`"test"` → `"Launch 36 - Unified Onboarding"`, was returning INCOMPLETE); **202 tests all green**.
  - **CLAUDE.md hierarchy (6 changes):**
    - Root `CLAUDE.md` rewritten: −38 lines; removed duplicate "Design Review Mode"; collapsed status prose → 5-line summary + roadmap pointer; fixed `186+` → `202`; added `scripts\check_all.ps1`; added scoped-loading map table.
    - Created `src/rrr/orchestration/CLAUDE.md` — scoring pipeline map, LangGraph entry point, gate engine rule, ADR guard (fills missing layer coverage).
    - Created `adr/CLAUDE.md` — ADR count, quick-reference format, proposed ADRs list.
    - Fixed `.claude/rules/adr-lifecycle.md` — added `globs: ["adr/*.md"]` (was always-loading every session, bug fixed).
    - Fixed `.claude/rules/test-coverage.md` — narrowed globs to `tests/**/*.py` only (was also firing on all src edits).
    - Fixed `scripts/check_alignment.py` — excluded `adr/CLAUDE.md` from ADR count (same pattern as `diagrams/README.md`).
  - **Context budget:** always-loaded context ~780 → ~420 lines for docs/config sessions; specialist rules load only when the matching directory is entered.
- **Pending / next:** `--dry-run` flag (M2 sole remaining item).
- _Metrics: 202 tests · comments+ruff+mypy+pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M4 ✅, M2 🔄 (dry-run pending)_

### 2026-06-20 — **LangGraph wrapper + MockLLMProvider + Docker + RDE Senior Cert gap closure**
- **Planned:** RDE certification gap analysis → step-wise plan → execute.
- **Completed:**
  - **`docs/vision.md`** — "Alternatives Explored & Excluded" section (8 alternatives, PF-3 rubric gap closed).
  - **`docs/architecture-review.md`** — marked CI/CD ✅, pre-commit ✅, optional deps ✅, LocalLLMProvider ✅, MockLLMProvider ✅, LangGraph ✅ as resolved.
  - **`MockLLMProvider`** (`src/rrr/providers/mock_llm.py`) — fixture-backed, full guardrail chain, no model needed; `ProviderType.MOCK_LLM`; `MockLLMConfig`; `configs/demo.yaml`; `tests/fixtures/llm_responses/` (6 JSON fixtures); 10 tests.
  - **LangGraph StateGraph wrapper** (`src/rrr/orchestration/graph.py`) — two-node `dispatch → collect`; ThreadPoolExecutor inside dispatch; `pipeline.assess()` calls `run_assessment_graph()`; ADR-0002 implementation note added; 6 tests.
  - **Docker deployment** — `Dockerfile` (multi-stage, Python 3.11-slim, non-root `rrr` user) + `docker-compose.yml` (optional Ollama sidecar, named volumes) + `.dockerignore`.
  - **`docs/enterprise-deployment.md`** — 90-day engagement cycle, client persona, data source mapping, deployment topology (single-machine → K8s), client uplift artifacts, AI interview Q&A.
  - **`scripts/check_all.ps1`** — PowerShell gate wrapper (comments → ruff → mypy → pytest).
  - All docs updated: CLAUDE.md, architecture.md, roadmap.md, ai-usage.md (Stage 3f).
- **Pending / next:** `--dry-run` flag (M2). RDE Senior Certification submission.
- _Metrics: 186+ tests · comments+ruff+mypy+pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M4 ✅, M2 🔄 (dry-run pending)_

### 2026-06-19 — **M2 PlanRenderer + Chroma RAG (optional, 6D) + W5 E2E coverage + pre-commit**
- **Planned:** `.pre-commit-config.yaml`; M2 action-plan generator; Chroma RAG spike; W5 coverage-aware E2E; ADR-0017.
- **Completed:**
  - **`.pre-commit-config.yaml`** — four local hooks (comment-coverage, ruff-check, ruff-format, mypy); activates on `git init && pre-commit install` (project has no `.git`). CI provides equivalent automated gate.
  - **M2 action-plan generator** — `PlanRenderer` + `action_plan.md.j2`; `rrr --format plan` emits CRITICAL/MAJOR/MINOR-bucketed pre-release checklist with `- [ ]` remediation checkboxes, unavailable-dimension re-assessment table, and re-run instruction footer; 9 tests. `src/rrr/output/__init__.py` exports both renderers.
  - **Chroma RAG** — `chromadb` 1.5.9 confirmed on Python 3.14.4/Windows. `AssessmentStore(chroma_path=...)` optional integration: 6D score vector `[scope, estimation, environment, test_readiness, dependency, score/100]`, cosine distance, `":memory:"` for test isolation (UUID-suffixed collection to handle EphemeralClient singleton), best-effort `save()` + `similar_to(k=3)`; `config.memory.chroma_path: null` disables silently; 4 new tests. ADR-0007 impl-noted. `pipeline.run_and_record` wired.
  - **W5 coverage-aware E2E sub-score** — `TestReadinessAssessor._composite`: denominator is `max(run, planned)` so unrun tests count as failures (was `run` only). Input-freshness guard: `freshness_max_age_days: 30` in config; MINOR risk if snapshot older than threshold; `_check_freshness` helper. All 4 existing TR tests still green; golden g1/g5 tolerances satisfied.
  - **ADR-0017** — already existed and complete (`adr/0017-make-ai-earn-its-place.md`). Confirmed Proposed status and no further action required.
- _Metrics: 186 tests · comments+ruff+mypy+pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M4 ✅, M2 🔄 (renderer ✅, PlanRenderer ✅, dry-run pending)_

### 2026-06-19 — **M4 fully complete + M2 Jinja2 renderer + GitHub Actions CI**
- **Planned:** W6 retry (configurable backoff), M2 Jinja2 templates, GitHub Actions CI.
- **Completed:**
  - **W6 retry on transient `ToolInvocationError`** — `ToolsConfig` (`retry_count`, `retry_backoff_s`) Pydantic-validated in config; `ToolRunner` carries config; `BaseAssessor.invoke_tool` retry loop; `ToolTimeoutError` explicitly excluded; 3 new tests. **W6 fully closed, M4 ✅ complete.**
  - **M2 Jinja2 readiness-plan renderer** — `src/rrr/output/` (`MarkdownRenderer` + `verdict_report.md.j2`); `rrr --format markdown` CLI flag (backward-compat: `--verbose` still emits JSON); 11 tests.
  - **GitHub Actions CI** — `.github/workflows/ci.yml`; runs comment-linter → ruff → mypy --strict → pytest on Python 3.11 + 3.12 on every push/PR.
- **Pending / next:** M2 dry-run / action-plan generator; W5 coverage-aware E2E; Chroma RAG (deferrable to M5).
- _Metrics: 173 tests · comments+ruff+mypy+pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M4 ✅, M2 🔄 (renderer ✅, dry-run pending)_

### 2026-06-18 — **M4 hardening complete + W6 timeout + demo script + comment linter**
- **Planned:** ADR-0014 GateEngine + ADR-0015 required-dims/confidence-floor; comment retrofit + standards; W6 timeout; demo script.
- **Completed:**
  - **ADR-0014 GateEngine** — `src/rrr/orchestration/gate_engine.py`; named gate signals on `RiskFactor.gate`; `gates:` config block now load-bearing; 12 new tests.
  - **ADR-0015 required-dims + confidence-floor** — `thresholds.required_dimensions` + `thresholds.confidence_floor`; GO→CONDITIONAL if required dim missing or aggregate confidence below floor; `aggregate_confidence` surfaced in CLI; 8 new tests.
  - **`LocalLLMProvider`** — Ollama HTTP on `127.0.0.1`, stdlib urllib, full guardrail chain; 14 tests.
  - **W6 structured logging** — run-id per assessment, provider timing per dimension, fallback warnings.
  - **W6 per-assessor hard timeout** (NFR-1) — `_fan_out` now uses `wait(timeout=assessor_default)`; timed-out assessors marked unavailable; `shutdown(wait=False)` prevents CLI hang; 3 new tests.
  - **`scripts/run_demo.ps1`** — end-to-end demo runs all 5 golden fixtures, verifies verdict+score vs oracles; 5/5 PASS verified.
  - **Full codebase comment retrofit** — all 33 `src/rrr/` modules at docstring standard.
  - **`.claude/rules/comment-standards.md`** + **`scripts/check_comments.py`** — auto-loaded rule + stdlib AST linter; integrated into SOD + EOD gate.
  - **Comment standard added to SOD/EOD routines** — `check_comments.py` runs at session start and before log entry.
  - Tests: **125 → 159** (+34). All four gates green: comments + ruff + mypy --strict + pytest.
- **Pending / next:** Chroma RAG (deferrable, native-build spike); retry on transient tool failure (W6 remainder); M2 Jinja2 templates.
- _Metrics: 159 tests · comments+ruff+mypy+pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M3 ✅, M4 🔄 (GateEngine ✅, required-dims ✅, LocalLLMProvider ✅, W6 ✅, demo ✅, Chroma deferred)_

### 2026-06-17 — **M4 eval harness complete; ADR-0014/0015 Accepted**
- **Planned:** M4 evaluation harness (FR-26/27/28) — author g2–g5 `ideal.json` oracles, then build deterministic metrics.
- **Completed:**
  - **All 5 golden oracles authored** (`g2`–`g5` `ideal.json`) — ground truth for verdict, score, risk factors, and dimension scores across all fixture types.
  - **Evaluation harness** (`tests/eval/`): `run_eval.py` (fixture runner), `metrics.py` (verdict accuracy, macro-F1, score MAE, risk-F1), `test_eval.py` (pytest integration). Results: verdict accuracy **100%**, macro-F1 **1.000**, all dim score MAEs **0.000**, mean risk-F1 **0.80**. LLM-as-judge deferred to Phase 2 per ADR-0008.
  - **ADR-0014** (centralized `GateEngine`) + **ADR-0015** (required-dims + confidence-floor) promoted **Proposed → Accepted** with concrete implementation notes (interface, config additions, calibration against golden set). Implementation deferred to M3-hardening sprint.
  - Tests: **110 → 125** (+15 eval harness tests). Ruff format alignment of 3 eval files in EOD pass.
- **Pending / next:** M3-hardening — **ADR-0014 `GateEngine`** + **ADR-0015 required-dims/confidence-floor** (Accepted, impl deferred); **`LocalLLMProvider`** demo path; Chroma RAG spike (deferrable).
- _Metrics: 125 tests · ruff + mypy --strict + pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M3 ✅, M4 🔄 (eval harness ✅, ADR-0014/0015 Accepted, impl pending)_

### 2026-06-16 — **M3 complete + M4 underway: the tool runs end-to-end** 🎉
- **Planned:** Build the five concrete assessors + orchestrator (M3), then start M4.
- **Completed:**
  - **All 5 assessors** on `BaseAssessor` — Scope (FR-1), Estimation (FR-2), TestReadiness (FR-4),
    Environment (FR-3), Dependency (FR-5); plus the shared env/dep `source_reader` (JSON/CSV/API).
    Each verified against real golden fixtures.
  - **Orchestrator** (`src/rrr/orchestration/`) — parallel fan-out, weighted score + redistribution,
    ADR-0013 veto/cap gates, verdict synthesis. **Engine verified: g1→GO/96, g2→NO_GO (E2E floor),
    g5→CONDITIONAL (scope creep).**
  - **Hypothesis property tests** (6 invariants) → **M3 ✅ complete.**
  - **M4 started:** Click **CLI** (`rrr --release …`, exit codes) + composition root
    `pipeline.assess()`; **SQLite persistence** (`AssessmentStore`, retry) + **trend comparison**
    (`compute_trends`, FR-9) via `run_and_record`.
  - Tests **52 → 110**; ruff + mypy --strict green throughout.
  - **Docs/diagrams/memory alignment pass** — reconciled every artifact with the as-built state:
    rewrote CLAUDE.md "Current status" + structure/stack; added an "Implementation status" callout to
    architecture.md; populated ai-usage.md (Implementation/Testing/Docs stages); added an
    impl-status note to ADR-0002 (LangGraph deferred) + the orchestration diagrams; consolidated the
    project-state memory. Fixed a propagated miscount (**9 diagrams**, not 10) and stale "Phase 3"/
    "no implementation" strings. Recorded the two deviations (LangGraph→ThreadPoolExecutor;
    gates-via-risk-severity).
  - **Design review** (senior-architecture pass) → logged 4 **Proposed** ADRs (0014 gate engine ·
    0015 verdict robustness · 0016 assessment-model v2 · 0017 make-AI-earn-its-place) + a roadmap
    "Design-review actions" backlog (W1–W6 + model-v2); enriched `ai-usage.md` (Stage 0 ideation +
    the "not-actually-AI-first" pivot).
  - **EOD-ritual tooling** — `scripts/check_alignment.py` (git-free drift check), the `/eod` command,
    the single "▶ Next action" pointer, and the per-entry metrics line; expanded the EOD convention
    into a 5-step daily project-sync (gate → align → log → next-action → artifact sync).
- **Pending / next:** M4 **evaluation harness** (FR-26/27/28) — needs `g2`–`g5` `ideal.json` oracles
  authored first; **Chroma RAG** spike (native-build risk on Py 3.14); demo. (LLM-judge → Phase 2.)
- _Metrics: 110 tests · ruff + mypy --strict + pytest green · alignment PASS (17 ADRs / 9 diagrams) · M1–M3 ✅, M4 🔄_

### 2026-06-15 — **M1 Foundations complete** 🎉
- **Planned:** Take stock of progress; set up daily tracking; then continue M1 (config → tools →
  providers → `BaseAssessor`).
- **Completed:**
  - Set up this EOD log + milestone table; corrected stale docs (13 ADRs / 9 diagrams).
  - **De-conflicted the "Phase" terminology** across all docs — "Phase" now means only
    local→external (Phase 1/2); RRP/RRR are scope groupings on milestones M1–M5.
  - **`ConfigLoader` + config schema** (`src/rrr/config/`) — deep-merge, weights-sum & gate-cap
    validation, local-first host allow-listing, `ConfigurationError`. *(11 tests)*
  - **Tool layer** (`src/rrr/tools/`) — `BaseTool`, `ToolRunner` (threading timeout + invocation
    recording), `RKTBrainReader` with scope-creep history. *(13 tests)*
  - **Provider layer** (`src/rrr/providers/`) — `LLMProvider` interface, `RuleBasedProvider`,
    `parse_with_repair` guardrail; injection-safe request envelope. *(10 tests)*
  - **`BaseAssessor` ABC** (`src/rrr/assessors/`) — template method, FR-12 confidence, graceful
    degradation, guardrail fallback. *(9 tests)*
  - **M1 Foundations done** — 52 tests, ruff + mypy --strict green.
- **Pending / next:** **M3** — the five concrete assessors (Scope → Estimation → Environment →
  TestReadiness → Dependency) + LangGraph orchestrator → weighted score → verdict (ADR-0013 gates).
  Backlog: `g2`–`g5` `ideal.json` oracles; confirm hatchling ships `default_config.yaml` in wheels.

### 2026-06-14
- **Planned:** Start M1 Foundations — the Pydantic v2 model layer.
- **Completed:** Built `src/rrr/models/` (8 modules: base, enums, brain, environment, dependency,
  evidence, dimension, llm, assessment); smoke tests against the real `g1` golden fixtures;
  quality gate green (**ruff · mypy --strict (18 files) · pytest**); roadmap checkbox + memory updated.
- **Pending / next:** `ConfigLoader`, `ToolRunner`/`RKTBrainReader`, `LLMProvider`/`RuleBasedProvider`,
  `BaseAssessor`, Jinja2 templates; `g2`–`g5` `ideal.json` oracles.

## Documentation
| Topic | Location |
|-------|----------|
| Vision & goals | [docs/vision.md](docs/vision.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Requirements (FR/NFR) | [docs/requirements.md](docs/requirements.md) |
| Roadmap & phases | [docs/roadmap.md](docs/roadmap.md) |
| Evaluation plan | [docs/evaluation-plan.md](docs/evaluation-plan.md) |
| AI usage log | [docs/ai-usage.md](docs/ai-usage.md) |
| Decisions (ADRs) | [adr/](adr/) |
| Diagrams | [diagrams/](diagrams/) |

## Getting started (Python 3.11+)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"        # core + dev tooling (local-first; no cloud deps)
# optional on-machine LLM path:
# pip install -e ".[dev,local-llm]"

pytest                          # run tests (727 tests)
ruff check src tests            # lint
mypy src                        # type-check
rrr --help                      # CLI entry point
```

## Verdict & exit codes
`rrr` prints e.g. `VERDICT: GO  SCORE: 84` (or full JSON with `--verbose`) and exits:
`0` = GO · `1` = NO_GO · `2` = CONDITIONAL · `3` = ERROR.

## Working with Claude Code
Project conventions and constraints live in [CLAUDE.md](CLAUDE.md) (auto-loaded) and
[.claude/project-context.md](.claude/project-context.md). Custom commands: `/plan-feature`,
`/adr`, `/check`.
