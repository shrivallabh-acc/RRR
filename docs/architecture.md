# Architecture — Release Readiness Results (RRR)

> **Implementation status (Phase 1 fully complete + Phase 2 complete + M6 complete + M7 Phase 2 Collect screen ✅ — 727 tests as of 2026-07-10).** This document
> describes the target Phase-1 architecture. What's **built & tested**: config, tool layer (with configurable
> retry), `RuleBasedProvider` + `LocalLLMProvider` + `MockLLMProvider` + `BedrockProvider` (ADR-0019) +
> **`ClaudeProvider`** (Anthropic Messages API, Phase 2, ADR-0006 — `pip install rrr[cloud]`, 13 tests) +
> guardrail chain, all 8 scored assessors + **9 gate-only assessors** (ADR-0016 items 2–3, 8–16: SecurityComplianceAssessor, PerformanceAssessor, AccessibilityAssessor, AuditabilityAssessor, DisasterRecoveryAssessor, DataReconciliationAssessor, FailureModeAssessor, DependencyRiskAssessor, ProductionReadinessAssessor, ArchitectureFitnessAssessor, ArchitectureDriftAssessor) + **OperabilityAssessor** (weight 0.07) + **ObservabilityAssessor** (weight 0.03) + **RollbackAssessor** (gate-only),
> **LangGraph StateGraph wrapper** (`orchestration/graph.py` dispatch→collect, ADR-0002 impl-noted 2026-06-20; `Orchestrator.collect()` extracted 2026-06-30 — production mechanism is ThreadPoolExecutor, LangGraph is optional tracing layer), orchestrator (weighted score +
> ADR-0013/0014 gates → verdict + aggregate confidence + **Release Risk Tiers** + ship-safety/delivery sub-scores), Click CLI (`--format text/json/markdown/plan`,
> `--dry-run`, `--list-releases`, `--tier hotfix|standard|major`), SQLite persistence + Chroma RAG (optional 6D vector, ADR-0007), trend
> comparison, evaluation harness (5 golden oracles, verdict accuracy 100%, macro-F1 1.00) + **structural
> judge** (`tests/eval/judge.py`, structural score 1.00 on all 5 fixtures, 2026-06-23) + **eval report**
> (`tests/eval/report.py`, `docs/eval-report.md`) + **prose quality judge** (`ProseQualityJudge`, FR-28, 2026-06-26), GitHub Actions CI, `.pre-commit-config.yaml`, Jinja2
> output layer (`MarkdownRenderer` + `PlanRenderer`), **Docker deployment** (`Dockerfile` + `docker-compose.yml`,
> `docs/enterprise-deployment.md`), **`rrr-ingest` HTML ingest layer** (ADR-0018, fuzzy release matching,
> `--list-releases`, real-data validated against OSM 41 releases),
> **`AbstractAssessmentStore` ABC** (`SQLiteAssessmentStore` local impl + `RemoteAssessmentStore` stub + `build_store()` factory, `config.memory.backend`),
> **`rrr-collect` CLI** (ADR-0023 Phase 1 — `CollectorRunner`, `CollectorRegistry`, `InteractiveCollector`, `rrr-collect` entry point — 32 tests, 2026-07-09),
> **`rrr-ui` Collect screen** (ADR-0023 Phase 2 — `_collect_panel()`, status/form sub-view, `_DictCollector` + `CollectorRunner.run()` shared write path, InputContract-driven NiceGUI widgets — 6 tests, 2026-07-10),
> **hardening bundle** (T-02 HTTP Basic Auth ASGI middleware + `UiConfig`; T-03 WAL mode in SQLiteAssessmentStore; T-04 `${VAR_NAME}` env-var interpolation in ConfigLoader; T-07 `PRAGMA user_version` schema migration guard — 13 tests, 2026-07-10).
> **One remaining deviation:** ADR-0013 gates are realized via risk-factor *severity*, not raw-data re-checks
> (keeps `DimensionResult` boundary clean).
> **M7 in progress (Phase 2 Collect screen ✅ 2026-07-10):** Remaining — tool adapters (snyk, sonarqube, k6, axe, grafana, datadog). Remote backend implementation (hosted persistence) pending host/auth design.

## Overview
RRR is an **AI-first, multi-agent, local-first** Python system that produces an auditable
release verdict (GO / NO-GO / CONDITIONAL / INCOMPLETE). It orchestrates **5 specialized
assessor agents** in parallel; each combines **deterministic scoring** (the numbers:
MAPE, pass rates, weighted sums) with **LLM reasoning** (the judgment: interpreting
ambiguous evidence, classifying edge cases, writing the rationale and remediation plan).
An orchestrator fuses the dimension scores into a weighted verdict, grounds it in
**historical context retrieved from a local vector store (RAG)**, persists the result,
and emits a fully-audited output.

**Phase 1 runs entirely on your machine with no external calls** (ADR-0010). Reasoning is
delegated to a swappable **`LLMProvider`** (ADR-0006): the default `RuleBasedProvider`
needs no model at all; a `LocalLLMProvider` (Ollama / llama.cpp on `127.0.0.1`) gives the
AI-first demo path, still fully on-machine. The Anthropic **Claude** provider sits behind
the same interface for **Phase 2** external scale-out only. Every provider returns
**Pydantic-validated structured output** (the guardrail), and the numeric **score is
always deterministic**, so the verdict stays reproducible regardless of provider.

## Where AI is used (and where it isn't)
| Concern | Deterministic (code) | `LLMProvider` (rule-based / local LLM / Claude) |
|---------|----------------------|-------------------------------------------------|
| Numeric scoring (MAPE, pass-rate, weighted sum) | ✅ reproducible math | — |
| Classifying *ambiguous* items (e.g. a capability at 51% with mixed signals) | threshold default | ✅ reasons over evidence |
| Scope-creep / risk detection narrative | flag raw signal | ✅ explains *why* it's a risk |
| Evidence narrative + remediation plan per dimension | — | ✅ generated, schema-validated |
| Verdict rationale (the "why") | verdict label from score | ✅ synthesizes the explanation |
| Historical/benchmark context | — | ✅ RAG over prior assessments (local Chroma) |
| Output validation / guardrail | ✅ Pydantic-validated provider output | — |

The split keeps the **score deterministic and reproducible** while using AI exactly where
human-style judgment adds value — and makes every AI output checkable.

## Component Diagram
_See [diagrams/](../diagrams/) for the rendered version._

```
                          ┌──────────────────────────┐
   brain/*.json  ───────► │       ConfigLoader        │ ◄── default_config.yaml
 (RKT Program Metrics)    │  (YAML → defaults → v2)   │     (provider/source = local)
   files / localhost ───► └────────────┬─────────────┘
                                       │
                          ┌────────────▼─────────────┐        ┌──────────────────┐
                          │       Orchestrator        │◄┄RAG┄┄│  Chroma (local)   │
                          │  (LangGraph StateGraph    │ (M4)   │  vector store(M4) │
                          │   dispatch→collect ✅)    │        └──────────────────┘
                          └────────────┬─────────────┘
            ┌──────────┬───────────────┼───────────────┬──────────┐
            ▼          ▼               ▼               ▼          ▼
        ┌───────┐ ┌──────────┐ ┌─────────────┐ ┌────────────┐ ┌────────────┐
        │ Scope │ │Estimation│ │ Environment │ │TestReadiness│ │ Dependency │  (BaseAssessor)
        └───┬───┘ └────┬─────┘ └──────┬──────┘ └─────┬──────┘ └─────┬──────┘
            │  each assessor: tools → deterministic score → LLMProvider.reason() → DimensionResult
            └──────────┴─────── DimensionResult ─────┴──────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │  Verdict + provider       │
                          │  rationale + remediation  │
                          └────────────┬─────────────┘
                       ┌───────────────┼────────────────┐
                       ▼               ▼                ▼
                  SQLite + Chroma   AssessmentOutputModel   CLI (Click)
                  (local history)   (JSON, schema 1.0.0)    exit codes / Jinja2 MD
```

## Components
| Component | Responsibility | Notes |
|-----------|----------------|-------|
| **ConfigLoader** | Load YAML, merge defaults, validate via Pydantic | `ConfigurationError` with full error list; weights sum to 1.0; holds provider selection, endpoints (local by default), prompt settings |
| **Orchestrator** | Fan-out 5 assessors in parallel, fan-in, score, derive verdict; ask the provider for the verdict rationale; (RAG retrieval = M4) | **Built**: `ThreadPoolExecutor` fan-out, weight redistribution, ADR-0013 gates. LangGraph `StateGraph` wrapper ✅ built 2026-06-20 (`orchestration/graph.py`, ADR-0002) |
| **BaseAssessor (ABC)** | `invoke_tool()`, `reason()` (via provider), `calculate_confidence()`, `build_evidence()`, `reset()` | All 5 extend this; emits `DimensionResult` |
| **LLMProvider (interface)** | `reason(prompt, schema) -> validated Pydantic model` | Impls: `RuleBasedProvider` (default, no model), `LocalLLMProvider` (Ollama/llama.cpp, local), `BedrockProvider` (AWS, Phase 2), `MockLLMProvider` (fixture-backed demo), `ClaudeProvider` ✅ built 2026-06-25 (Phase 2 opt-in). ADR-0006 |
| **5 Assessors** | Scope, Estimation, Environment, Test Readiness, Dependency | Deterministic score + provider reasoning per [requirements.md](requirements.md) FR-1…FR-5 |
| **BaseTool (Protocol)** | `name` + `invoke(**params)` | Modular — new tools without touching assessors |
| **ToolRunner** | Timeout (threading) + `ToolInvocationModel` recording | `ToolTimeoutError` / `ToolInvocationError` |
| **Memory (SQLite + Chroma)** | SQLite = canonical assessment records + history/trends; Chroma (embedded) = summaries for RAG/benchmark | **Built**: `AssessmentStore` (SQLite, retry persist 3× / 5s). Chroma RAG = M4 (planned) |
| **Output layer** | `AssessmentOutputModel` JSON, CLI text, Jinja2 Markdown | **Built**: CLI verdict line + `--verbose` JSON (schema "1.0.0"). Jinja2 Markdown = M2 (planned) |

## Data Flow
1. **Load** — ConfigLoader reads `default_config.yaml` + overrides; validates (Pydantic v2); provider + data sources default to local.
2. **Ingest** — `brain/*.json` snapshots + environment/dependency data (local files or `127.0.0.1` mock APIs).
3. **Fan-out** — Orchestrator dispatches all 5 assessors in parallel.
4. **Assess** — each assessor: invoke tools (recorded + timed) → compute deterministic score → `LLMProvider.reason()` to classify ambiguous items, extract risk factors, and write the evidence narrative (schema-validated) → compute confidence → `DimensionResult`.
5. **Fan-in** — collect results; redistribute weight for any unavailable dimension.
6. **RAG** — orchestrator queries local Chroma for the most similar prior releases to ground trend/benchmark context.
7. **Verdict** — weighted sum → GO/NO-GO/CONDITIONAL/INCOMPLETE; provider synthesizes the verdict rationale + cross-dimension remediation plan (schema-validated).
8. **Persist** — write to SQLite (with retry); embed a summary into Chroma for future RAG.
9. **Emit** — `AssessmentOutputModel` JSON, CLI verdict line / `--verbose`, exit code, optional Markdown.

## Key Decisions
ADRs in [adr/](../adr/):
- ADR-0001 — Record architecture decisions
- ADR-0002 — LangGraph for agent orchestration
- ADR-0003 — SQLite for canonical persistence
- ADR-0004 — Pydantic v2 for all data models
- ADR-0005 — Graceful degradation via weight redistribution
- ADR-0006 — `LLMProvider` abstraction (local-first; rule-based default / local LLM / Claude)
- ADR-0007 — Chroma vector store for memory + RAG benchmarking (local)
- ADR-0008 — Evaluation: golden dataset + F1 + LLM-as-judge
- ADR-0009 — Guardrails via Pydantic structured outputs + repair loop
- ADR-0010 — Local-first: no external runtime dependencies (Phase 1)
- ADR-0011 — Dimension weight split (quality & delivery weighted)
- ADR-0012 — Brain input contract & RKT anti-corruption boundary
- ADR-0013 — Verdict veto/cap gates (critical single-dimension failures ceiling the verdict)
- ADR-0014 — Centralized, config-driven gate engine — *Proposed* (2026-06-16 review)
- ADR-0015 — Verdict robustness: required dimensions + confidence-aware capping — *Proposed*
- ADR-0016 — Assessment model v2: new + gate-only dimensions, release risk tiers — *Proposed*
- ADR-0017 — Make the AI earn its place: bounded LLM role + eval-gated adoption — *Proposed*

## Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM hallucination / invalid output | Untrustworthy verdict | All provider calls return **Pydantic-validated** output; on failure, one repair retry then fall back to `RuleBasedProvider` for that dimension + reduced confidence (ADR-0009) |
| Non-deterministic LLM → non-reproducible verdict | Loss of trust | **Score is deterministic**; provider only writes rationale/classification. Verdict label derives from the numeric score, not free-form text |
| Accidental external call | Breaks local-first guarantee | Default config is local-only; non-local endpoints rejected unless explicitly allowlisted (ADR-0010); CI runs offline |
| Local LLM hardware cost / unavailable | Can't run AI path | `RuleBasedProvider` default needs no model — system always runs; local LLM is opt-in |
| Upstream `brain/*.json` schema drift | Assessors misread data | Pydantic validation at ingest; fail that dimension, degrade gracefully |
| Localhost source slow or down | Assessment stalls | Source timeouts (10s env / 60s assessor); fall back to file input |
| One assessor crashes | Loss of verdict | Weight redistribution; verdict stands if ≥`minimum_assessors` succeed |
| Misconfigured weights (≠ 1.0) | Skewed scores | ConfigLoader rejects with detailed `ConfigurationError` |
| Prompt injection via ingested data | Manipulated verdict | Ingested data passed as data, never instructions; system prompt fixed; outputs schema-constrained |
