# CLAUDE.md — Release Readiness Results (RRR)

> Auto-loaded every session. High-signal only — detail lives in the docs it points to.

## What this project is
RRR is an **AI-first, local-first** Python CLI that turns release metrics into an auditable
**GO / NO-GO / CONDITIONAL / INCOMPLETE** verdict. It consumes `brain/*.json` snapshots from
**RKT Program Metrics**, adds environment-readiness and dependency-health dimensions, and
produces a **deterministic score** with LLM-driven reasoning, backed by a full audit trail.

Read these before non-trivial work:
- Vision → [docs/vision.md](docs/vision.md)
- Architecture → [docs/architecture.md](docs/architecture.md)
- Requirements (FR/NFR) → [docs/requirements.md](docs/requirements.md)
- Roadmap & phases → [docs/roadmap.md](docs/roadmap.md)
- Decisions → [adr/](adr/) · Diagrams → [diagrams/](diagrams/)

## How to work here
@.claude/project-context.md
@.claude/rules/comment-standards.md

**Principal architect first, engineer second.** For significant requests use the 8-section format
(Understanding → Assumptions → Analysis → Recommended Approach → Implementation Plan →
Risks & Trade-offs → Code Changes → Validation Strategy). Read files before proposing changes.

### Scoped rules — what loads when
Rules and orientation load automatically based on where you are working:

| Layer | Mechanism | What loads |
|-------|-----------|------------|
| `src/rrr/assessors/` | glob rule | assessor pattern (BaseAssessor, severity→gate, FR-12) |
| `src/rrr/models/` | glob rule | model conventions (frozen vs. mutable, Field requirements) |
| `src/rrr/providers/` | glob rule | provider guardrail chain (ADR-0009, local-first ADR-0010) |
| `src/rrr/orchestration/` | CLAUDE.md | scoring pipeline map + LangGraph orientation |
| `src/rrr/**` | glob rule | deterministic-first invariant (always-on for all src edits) |
| `tests/` | glob rule | test coverage requirements per layer |
| `adr/` | CLAUDE.md + glob rule | ADR lifecycle, format, current count |

## Hard constraints (Phase 1)
- **Local-first** (ADR-0010, NFR-8): no external network calls at runtime; `127.0.0.1`/`localhost` only.
- **Deterministic score** (ADR-0006): LLM writes rationale only; verdict label derives from numeric score.
- **Pydantic-validated output** (ADR-0009): one repair retry, then fall back to `RuleBasedProvider`.
- **Graceful degradation** (ADR-0005): verdict stands if ≥ `minimum_assessors` (default 3) dimensions succeed.

## Tech stack
Python 3.11+ (dev: **3.14**) · Pydantic v2 · SQLite · Click · PyYAML · pytest + Hypothesis.
**LangGraph** `StateGraph` wrapper (`orchestration/graph.py`, dispatch→collect, optional `rrr[graph]`).
**Chroma** embedded RAG (optional, `rrr[rag]`, ADR-0007). **Jinja2** Markdown output.
**MockLLMProvider** (fixture-backed offline demo). **LocalLLMProvider** (Ollama on `127.0.0.1`).
`ClaudeProvider` (`claude-sonnet-4-6` default, `pip install rrr[cloud]`) is Phase 2 opt-in (built 2026-06-25).

## Project structure
```
src/rrr/
  config/        ConfigLoader + default_config.yaml
  models/        Pydantic v2 data models (DimensionResult, Evidence, AssessmentOutput, LLM I/O)
  providers/     LLMProvider interface + RuleBased / LocalLLM / MockLLM / Claude (Phase 2)
  tools/         BaseTool protocol + ToolRunner (timeout + invocation recording)
  assessors/     BaseAssessor ABC + Scope, Estimation, Environment, TestReadiness, Dependency, Operational, Security, Performance
               (M6: split Operational → Operability/Observability/Rollback; 9 new gate-only assessors: Accessibility, Auditability, DisasterRecovery, DataReconciliation, FailureMode, DependencyRisk, ProductionReadiness, ArchitectureFitness, ArchitectureDrift)
  orchestration/ LangGraph StateGraph wrapper + scoring + verdict/gates + trends
  memory/        SQLite AssessmentStore + Chroma RAG (optional)
  ingest/        HTMLExtractor + BrainWriter + rrr-ingest CLI (ADR-0018)
  collectors/    BaseCollector + CollectorRunner + CollectorRegistry + InteractiveCollector + rrr-collect CLI (ADR-0023, M7 Phase 1 ✅)
  ui/            NiceGUI dashboard — sidebar nav, Overview screen, Release Detail page, Collect screen (ADR-0020, optional `rrr[ui]`)
               (M7: Collect screen ✅ 2026-07-10 — "Collect" sidebar nav, FRESH/STALE/MISSING status view, InputContract-driven form view, _DictCollector shared write path)
  pipeline.py    composition root
  cli.py         Click entry point (exit codes 0=GO 1=NO_GO 2=CONDITIONAL 3=ERROR)
  output/        Jinja2 Markdown templates (MarkdownRenderer + PlanRenderer)
tests/  unit/ · property/ (Hypothesis) · golden/ (5 fixtures g1–g5) · eval/ · fixtures/llm_responses/
```

## Commands
```powershell
pip install -e ".[dev]"                        # install package + dev tooling
scripts\check_all.ps1                           # full quality gate (one-liner)
pytest                                          # tests only
ruff check src tests                            # lint
ruff format src tests                           # format
mypy src                                        # type-check (NFR-5)
python scripts/check_comments.py src/rrr        # comment coverage
python scripts/check_alignment.py               # ADR/diagram/module count alignment
rrr --release "<ir_name>"                       # run assessment (--config, --value-stream, --verbose)
rrr-ingest --html-dir input --brain-dir brain --value-stream "<name>"  # HTML → brain JSON
rrr-collect --status                             # pre-flight data freshness check (all dims)
rrr-collect --release "<ir_name>" --all         # collect all dimension data interactively
rrr-collect --release "<ir_name>" --dimension operability  # collect one dimension
rrr-ui [--port 8080] [--value-stream "<name>"]  # web dashboard (requires pip install rrr[ui])
```
> Run tools via `.venv/Scripts/python.exe -m <tool>`. Full gate: **comments → ruff → mypy → pytest** — all four must pass before marking work complete.

## Conventions
- **src-layout**: import as `from rrr...`; all public functions fully type-hinted (NFR-5).
- **Pydantic v2** models everywhere; no anemic dicts crossing module boundaries.
- New tools → `BaseTool`; new assessors → `BaseAssessor` — extend without modifying core (NFR-7).
- Significant design decisions → new ADR in `adr/`; update roadmap checkboxes when work lands.
- Timestamps: ISO 8601, millisecond precision (NFR-3).

## Current status
**M1–M6 complete. Phase 1 fully complete. Phase 2 complete. M7 🔄 (ADR-0023 Accepted; Phase 1 ✅ 2026-07-09; Phase 2 Collect screen ✅ 2026-07-10; adapters batch 1 ✅ 2026-07-16; batch 2 ⬜).** 23 ADRs. 766 tests (last gate run), all green. Golden-fixture proof:
g1→GO/97, g2→NO_GO, g3→CONDITIONAL/74, g4→INCOMPLETE, g5→CONDITIONAL/93.
Codebase cleanup + comprehensive docs ✅ 2026-07-26 — `RemoteAssessmentStore` stub removed (all methods raised `NotImplementedError`; `MemoryConfig.backend` narrowed to `Literal["sqlite"]`); orphaned `data/operational.json` deleted (dimension renamed to `operability` in ADR-0016 item 7); comprehensive `README.md` rewritten covering all 4 CLIs, all 21 assessors, full config reference, output formats, tiers, LLM providers, and web dashboard; 14 per-folder `README.md` files added across `src/rrr/` subpackages, `tests/`, `data/`, `configs/`. 766 tests (1 fewer: removed `test_remote_store_satisfies_interface_and_raises_on_write`).
M7 adapters batch 1 ✅ 2026-07-16 — `src/rrr/collectors/adapters/` subpackage: `K6Adapter` (k6 `--summary-export` JSON → `PerformanceInput`), `SnykAdapter` (`snyk test --json` subprocess → `SecurityInput`), `SonarQubeAdapter` (`/api/issues/search` REST → `SecurityInput`); 40 offline unit tests; env-var credentials, no network in tests.
M7 Phase 2 Collect screen ✅ 2026-07-10 — `_collect_panel()` in `src/rrr/ui/app.py`: status view (FRESH/STALE/MISSING badge per dimension, Refresh); form view (InputContract-driven NiceGUI widgets: Enum→select, bool→switch, int/float→number, str→input); Save via `_DictCollector` + `CollectorRunner.run()`; `collect_status_all()`, `load_collect_form_data()` pure helpers; `_unwrap_collect_optional()`, `_build_collect_field_widget()` type-dispatch; "Collect" sidebar nav item (admin section). ADR-0020 impl-note 2026-07-10; ADR-0023 Phase 2 impl-note 2026-07-10. 6 new unit tests.
T-02+T-03+T-04+T-07 hardening bundle ✅ 2026-07-10 — WAL mode (T-03): `PRAGMA journal_mode=WAL` on every `SQLiteAssessmentStore` open; schema migration guard (T-07): `_SCHEMA_VERSION`/`_MIGRATIONS` pattern with `PRAGMA user_version`; env-var interpolation (T-04): `${VAR_NAME}` substitution in config YAML before Pydantic validation; HTTP Basic Auth (T-02): `UiConfig(auth_user, auth_password)` in schema + `_setup_basic_auth()` ASGI middleware on NiceGUI; 13 new tests.
M7 Phase 1 collectors ✅ 2026-07-09 — `src/rrr/collectors/` package: `BaseCollector` ABC, `CollectorRunner` (`status()`/`run()`), `CollectorRegistry` (14 supplementary dimensions), `InteractiveCollector` (Pydantic schema → Click prompts), `rrr-collect` CLI (`--status`/`--dimension`/`--all`/`--refresh`/`--skip-optional`/`--tier`/`--data-dir`); 32 new tests. `rrr-collect --status` operational.
9 gate-only assessors (ADR-0016 items 8–16) ✅ 2026-07-09 — `AccessibilityAssessor`, `AuditabilityAssessor`, `DisasterRecoveryAssessor`, `DataReconciliationAssessor`, `FailureModeAssessor`, `DependencyRiskAssessor`, `ProductionReadinessAssessor`, `ArchitectureFitnessAssessor`, `ArchitectureDriftAssessor`; 9 `InputContract` models; 9 source readers; 9 `data/<dim>.json` stubs; 9 opt-in `DataSource | None` fields in `SourcesConfig`; 143 new tests. M6 complete.
OperationalAssessor split (ADR-0016 item 7) ✅ 2026-07-09 — `OperabilityAssessor` (weight 0.07, always-on); `ObservabilityAssessor` (weight 0.03, opt-in); `RollbackAssessor` (gate-only, opt-in). `OperabilityInput`, `ObservabilityInput`, `RollbackInput` models; 3 new source readers; weights rebalanced (operational 0.10 → operability 0.07 + observability 0.03); `SourcesConfig.operability` required, `.observability`/`.rollback` opt-in; golden fixtures updated (all 5); 66 new tests.
Release Risk Tiers + ship-safety/delivery-performance split (ADR-0016 items 4–6) added 2026-07-09 — `ReleaseRiskTier` enum; `TierThresholds`/`TiersConfig` models; `tiers:` default config block; `--tier` CLI flag; `score_band()` takes explicit go/no_go; `triggered_caps()` `excluded_dims`; `derive_verdict()` tier-aware; `split_scores()` sub-scores; `AssessmentOutputModel` `tier`/`ship_safety_score`/`delivery_performance_score` fields; Markdown + text output updated; 29 new tests.
PerformanceAssessor (ADR-0016 item 3) added 2026-07-01 — gate-only (weight=0); load-test/SLO/capacity gates; 25 new tests.
Ingest layer (ADR-0018): `rrr-ingest` HTML→brain converter done 2026-06-22 (29 tests, real OSM data validated).
Fuzzy release matching + `--list-releases` added 2026-06-22.
BedrockProvider (ADR-0019) added 2026-06-22 — Amazon Bedrock Converse API via boto3 (Phase 2).
ClaudeProvider (ADR-0006) added 2026-06-25 — Anthropic Messages API via anthropic SDK (Phase 2, `pip install rrr[cloud]`).
ProseQualityJudge (FR-28, ADR-0008) added 2026-06-26 — live-LLM prose scoring; FR-28 fully closed; eval report §4 added.
NiceGUI dashboard (ADR-0020) added 2026-06-26 — `rrr-ui` command, release browser + history panel (`pip install rrr[ui]`); smoke-tested against 41 real OSM releases 2026-06-28.
Live external APIs ✅ 2026-06-28 — `ApiSource` HTTP transport tested (19 new tests); `data/operational.json` stub added; M5 live APIs roadmap item closed.
Trends tab in `rrr-ui` ✅ 2026-06-28 — third tab with release selector + ECharts score-over-time chart; `AssessmentStore.assessed_releases()`; `score_history_data()` helper; 9 new tests.
TOC value-stream tagging (ADR-0021) added 2026-06-28 — `HTMLExtractor` parses TOC slide; `toc_value_stream` added to `ReleaseRecord`; Trends tab filter replaced with TOC-based VS buttons; `list_toc_value_streams()` added to `RKTBrainReader`; 14 new tests.
Releases/History panel TOC grouping added 2026-06-28 — Releases panel groups by TOC VS (expansion panels); History panel gets VS filter buttons + `_render_records()` rebuild pattern.
Programme-first selection model (ADR-0022) added 2026-06-29 — `rrr-ui` auto-scans `brain/`; `--value-stream` removed from `rrr-ui` CLI; programme filter row added to all three panels (Releases/History/Trends); `list_datasets()` + `list_programmes()` helpers; dataset picker in header when multiple brain files exist; 8 new tests.
Security & Compliance gate-only dimension (ADR-0016 item 2) added 2026-06-29 — `SecurityComplianceAssessor` (weight=0; CRITICAL/MAJOR risk factors only); `SecurityInput`, `SecuritySourceReader`, `SastStatus`, `DastStatus` enums; `SecurityAssessorConfig` (high_cve_threshold=5); opt-in via `sources.security` config; `data/security.json` stub; 23 new tests.
Release Detail panel in `rrr-ui` ✅ 2026-06-29 — `_releases_panel()` rewritten as two-pane `ui.splitter()` master-detail; five-tab right pane (Overview/Environment/Dependencies/Security/Assessments); 4 new pure-Python data helpers; 10 new tests (ADR-0020 impl-note 2026-06-29).
`rrr-ui` UI redesign ✅ 2026-06-29 — `src/rrr/ui/app.py` completely rewritten; persistent left sidebar (140 px) + content-area navigation; Overview home screen (4-stat summary + sortable release table); Release Detail single-scroll page (verdict hero → dimension scorecard → risk factors → rationale → remediation → environment → dependencies → security → history); `_nav_item`, `_stat_card`, `_overall_trend`, `_overview_panel`, `_release_detail` added; old two-pane splitter and nested tabs removed.
ADR-0017 Accepted 2026-06-30 — "make-AI-earn-its-place" closed: narrative-only LLM (deliberate deviation from proposed classification adjudication); `ProseQualityJudge` is the eval gate (FR-28).
`AbstractAssessmentStore` ABC extracted 2026-06-30 — `SQLiteAssessmentStore` (local impl, `AssessmentStore` alias); `RemoteAssessmentStore` stub; `build_store()` factory; `config.memory.backend`; 3 new tests. M5 hosted persistence interface ✅.
LangGraph architecture resolved 2026-06-30 (ADR-0002 impl-note) — ThreadPoolExecutor confirmed as production mechanism; LangGraph is optional tracing/viz layer; `Orchestrator.collect()` extracted eliminating ~80-line duplication in `graph.py` `collect_node`.
One recorded deviation: ADR-0013 gates realized via risk-factor severity.
→ Full build history and remaining items in [docs/roadmap.md](docs/roadmap.md).
