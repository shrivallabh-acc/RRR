# RRR Deep Architecture & AI Review

> Reviewed: June 2026 | Reviewer context: Senior AI Engineer / Enterprise AI Architect
>
> **Implementation updates (2026-06-17):** Several findings below were resolved after the review.
> Each resolved item is marked **✅ RESOLVED** inline with a dated note.
> ADR count at review time: 13 (now 23 — ADR-0014 through ADR-0023 added post-review).

---

## A. Executive Summary

### What the project is
RRR (Release Readiness Results) is an AI-first, local-first Python CLI that synthesizes release metrics from five independent assessment dimensions (Scope, Estimation, Environment, Test Readiness, Dependency) into an auditable GO/NO-GO/CONDITIONAL/INCOMPLETE verdict. It separates deterministic scoring from LLM-generated reasoning, persists history to SQLite, and is designed to scale from a no-model default to local LLM to cloud Claude provider without rewriting anything.

### Overall Review Judgment
This is an exceptionally well-architected project that correctly applies the deterministic-first principle. The AI/deterministic boundary is clean, explicitly documented, and enforced by code. The `LLMProvider` abstraction with `RuleBasedProvider` as default is the textbook-correct pattern for enterprise AI systems. The project demonstrates genuine understanding of when LLMs add value (judgment, synthesis, narrative) versus when they don't (scoring, classification, validation).

### Top Strengths
1. **Deterministic/probabilistic split is correctly drawn** — score is always code, reasoning is always provider, verdict derives from score not prose
2. **Guardrail chain is production-grade** — Pydantic validation → repair retry → fallback → reduced confidence. No unvalidated LLM output reaches the user
3. **Claude Code developer ergonomics are excellent** — CLAUDE.md, project-context.md, custom commands, permissions model, house rules
4. **ADR discipline is strong** — 17 decisions with alternatives, all referenced in code and docs (13 at review time; ADR-0014/0015/0016/0017 added post-review)
5. **Property-based testing covers scoring invariants** — Hypothesis tests guard determinism, monotonicity, normalization, gate behavior
6. **Local-first hard constraint is enforced in code** — not just documented, actually rejected at runtime (pipeline.py line 35)

### Top Risks
1. ✅ **RESOLVED 2026-06-17 + extended 2026-06-23 + 2026-06-26 — Evaluation harness** — all 5 `ideal.json` oracles authored; `tests/eval/` built; verdict accuracy 100%, macro-F1 1.000. `StructuralJudge` ✅ built 2026-06-23. `ProseQualityJudge` ✅ built 2026-06-26 (FR-28 fully closed).
2. ✅ **RESOLVED 2026-06-19 — No CI/CD pipeline** — GitHub Actions CI added (`.github/workflows/ci.yml`, Python 3.11+3.12 matrix); `.pre-commit-config.yaml` (4 local hooks).
3. ✅ **RESOLVED 2026-06-19 — LangGraph + Chroma unused** — both moved to optional deps (`rrr[graph]`, `rrr[rag]`). LangGraph `StateGraph` wrapper ✅ built 2026-06-20 (ADR-0002). Chroma RAG ✅ built 2026-06-19 (ADR-0007).
4. ✅ **RESOLVED 2026-06-16 — No `.claude/rules/` directory** — six rules files created: `assessor-pattern.md`, `model-conventions.md`, `provider-pattern.md`, `deterministic-first.md`, `adr-lifecycle.md`, `test-coverage.md`
5. ✅ **RESOLVED — `LocalLLMProvider` and `ClaudeProvider` not implemented** — `LocalLLMProvider` ✅ built 2026-06-18 (Ollama HTTP, 14 tests). `ClaudeProvider` ✅ built 2026-06-25 (Anthropic Messages API, 13 tests, ADR-0006). `MockLLMProvider` ✅ built 2026-06-20.

### Maturity Ratings
| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| AI Architecture | 4.5 | Correct boundaries, justified patterns, clean interfaces |
| Production Readiness | 4.5 | Eval harness + structural judge ✅; CI/CD ✅ (GitHub Actions 2026-06-19); `LocalLLMProvider` ✅; `BedrockProvider` ✅ (2026-06-22); `ClaudeProvider` ✅ (2026-06-25); NiceGUI `rrr-ui` ✅ (2026-06-26) |
| Deterministic Enforcement | 5.0 | Exemplary — every deterministic concern is in code |
| Claude Code Optimization | 5.0 | Strong CLAUDE.md + commands + 6 rules/ files; hooks: ruff-on-edit (pre-existing) + comment-coverage-on-src-edit (added 2026-06-30) |
| Testing & Reliability | 4.5 | 727 tests (unit + property + eval harness ✅ + structural judge ✅ + prose judge ✅ 2026-06-26); M6 assessors ✅ 2026-07-09; M7 Phase 1 collectors ✅ 2026-07-09; M7 Phase 2 Collect screen ✅ 2026-07-10; hardening bundle ✅ 2026-07-10; CI/CD ✅; e2e demo ✅; FR-28 fully closed |
| Documentation | 4.5 | Comprehensive, honest about status, well-structured |

---

## B. Evidence-Based Findings

### Finding 1: Evaluation Harness — ✅ FULLY RESOLVED 2026-06-26
- **Original severity:** High
- **Resolution:** All 5 `ideal.json` oracles authored (`g1`–`g5`). `tests/eval/` package built: `metrics.py` (verdict accuracy, macro-F1, score MAE, risk-factor F1), `run_eval.py`, `test_eval.py` (13 tests). Results: verdict accuracy **100%**, macro-F1 **1.000**, all dim score MAEs **0.000**, mean risk-F1 **0.800**. LLM-as-judge (`judge.py`) deferred to Phase 2 per ADR-0008 — deterministic metrics satisfy the eval gate.
- **Extended 2026-06-23:** `StructuralJudge` built (`tests/eval/judge.py`) — offline CI-safe; checks narrative completeness, classification, confidence, rationale, risk-factor coverage; structural score 1.00 on all 5 fixtures. `EvalReportRenderer` built (`tests/eval/report.py`) — emits `docs/eval-report.md`. ADR-0008 impl-note added.
- **Extended 2026-06-26:** `ProseQualityJudge` built (`tests/eval/judge.py`) — live-LLM prose scoring using `ClaudeProvider`; scores clarity, specificity, actionability, evidence-grounding of each narrative via `ProseQualityResponse(RRRModel)`; API-key guard keeps CI offline-safe (returns `None` without `ANTHROPIC_API_KEY`). `EvalReportRenderer` extended with §4 prose quality table and gate entry. `run_eval.py` updated: `run_full_eval()` returns 3-tuple, `run_prose_eval()` added. FR-28 fully closed; ADR-0008 impl-note updated.
- **Remaining:** None — FR-28 fully implemented.

### Finding 2: No CI/CD Pipeline Definition — ✅ RESOLVED 2026-06-19
- **Original severity:** High
- **Resolution:** GitHub Actions CI added (`.github/workflows/ci.yml`); matrix: Python 3.11 + 3.12; runs `ruff check`, `mypy --strict`, `pytest` on every push/PR. Pre-commit hooks added (`.pre-commit-config.yaml`) with 4 local hooks: comment-coverage, ruff-check, ruff-format, mypy. Quality gate is now automated — not dependent on developer memory.

### Finding 3: Unused Heavy Dependencies in pyproject.toml — ✅ RESOLVED 2026-06-19
- **Original severity:** Medium
- **Resolution:** `chromadb` and `langgraph` moved to optional dependency groups in `pyproject.toml`. `chromadb` is now under `[project.optional-dependencies] rag = [...]`; `langgraph` under `[project.optional-dependencies] graph = [...]`. Core install is lean. Both are imported conditionally in code with graceful fallback (Chroma RAG optional via `chroma_path: null`; LangGraph wrapper falls back to `Orchestrator` if not installed). `pip install "rrr[rag,graph]"` installs both.

### Finding 4: `.claude/rules/` Enforcement Layer — ✅ RESOLVED 2026-06-16
- **Original severity:** Medium
- **Resolution:** Six rules files created in `.claude/rules/`: `assessor-pattern.md`, `model-conventions.md`, `provider-pattern.md`, `deterministic-first.md`, `adr-lifecycle.md`, `test-coverage.md`. Each is glob-triggered and enforces the patterns described in the original recommendation. Auto-loaded by Claude Code on matching file edits.

### Finding 5: Provider Implementations Missing — ✅ RESOLVED 2026-06-18
- **Original severity:** Medium
- **Resolution:** `LocalLLMProvider` implemented (`src/rrr/providers/local_llm.py`). Calls Ollama `/api/chat`
  on `127.0.0.1` via stdlib `urllib` (no SDK dep); host allow-list enforced at `__init__`; full
  `parse_with_repair` guardrail chain; network errors raise `ProviderValidationError` for the same
  graceful fallback path as validation failures. `pipeline.py` factory wired: `provider.type: local_llm`
  selects endpoint + model from `[provider.local_llm]` config block. 14 unit tests cover all paths.
- **Remaining (updated 2026-06-25):** `ClaudeProvider` ✅ RESOLVED — built 2026-06-25 (`src/rrr/providers/claude.py`, `pip install rrr[cloud]`, 13 tests). NiceGUI `rrr-ui` ✅ RESOLVED — built 2026-06-26 (ADR-0020). No further provider implementations pending for Phase 1.

### Finding 6: No Pre-commit Hooks or Git Automation — ✅ RESOLVED 2026-06-19
- **Original severity:** Low
- **Resolution:** `.pre-commit-config.yaml` added with 4 local hooks: `comment-coverage` (runs `scripts/check_comments.py src/rrr`), `ruff-check` (lint), `ruff-format` (format), `mypy` (type-check `src`). Hooks run on `pre-commit` stage. Activated via `pre-commit install`. Combined with GitHub Actions CI (Finding 2), the quality gate now runs at both commit-time and PR-time.

### Finding 7: Prompt Injection Surface is Well-Mitigated
- **Severity:** Low (positive finding)
- **Evidence:** `ReasoningRequest` in `providers/base.py` separates `facts` (data) from instruction; `allowed_classifications` bounds the label space; ingested data is never interpolated into system prompts; ADR-0009 documents the design
- **Why it matters:** This is the correct pattern for enterprise AI systems processing untrusted data
- **Recommended fix:** None needed. Document this as a deliberate security decision in the certification submission
- **Classification:** N/A — correctly implemented

### Finding 8: Excellent Deterministic Score Isolation
- **Severity:** Low (positive finding)
- **Evidence:** Every assessor's `_assess()` method returns `DeterministicAssessment` with the score computed from pure math. The `assess()` template method in `BaseAssessor` calls `_assess()` first, then `reason()` — the provider never touches the score. `orchestration/verdict.py` derives the verdict label from the numeric score
- **Why it matters:** This is the gold standard for hybrid AI/deterministic systems. The verdict is reproducible regardless of LLM behavior
- **Recommended fix:** None. This should be highlighted in the certification submission as evidence of the "deterministic where possible" principle
- **Classification:** N/A — correctly implemented

---

## C. Deterministic vs AI Opportunity Matrix

| Workflow / Capability | Current Approach | Recommended | Classification | Rationale | Priority |
|---|---|---|---|---|---|
| Numeric scoring (all 5 dims) | Deterministic code | Keep as-is | Deterministic | Math is reproducible, testable, auditable | — |
| Scope-creep detection | Deterministic threshold | Keep as-is | Deterministic | Simple comparison, no ambiguity | — |
| Risk factor extraction | Deterministic severity rules | Keep as-is | Deterministic | Based on thresholds, not judgment | — |
| Verdict derivation | Deterministic (score → band → gates) | Keep as-is | Deterministic | Must be reproducible | — |
| Weight redistribution | Deterministic math | Keep as-is | Deterministic | Sum normalization | — |
| Evidence narrative per dimension | LLMProvider (RuleBased default) | Justified AI | Single LLM call | Explains *why* a score is what it is | — |
| Verdict rationale synthesis | LLMProvider | Justified AI | Single LLM call | Cross-dimension synthesis needs reasoning | — |
| Remediation plan generation | LLMProvider | Justified AI | Single LLM call | Requires judgment about priorities | — |
| Ambiguous item classification | LLMProvider (future) | Justified AI | Single LLM call | 51% completion with mixed signals = judgment | — |
| RAG over historical assessments | Planned (Chroma, M4) | Justified AI | Single LLM call | Contextual grounding from history | Low |
| Config validation | Pydantic + code | Keep as-is | Deterministic | Schema enforcement | — |
| Output validation (guardrails) | Pydantic + repair loop | Keep as-is | Deterministic | Schema enforcement with retry | — |
| Quality gate (lint/type/test) | ✅ Automated (GitHub Actions 2026-06-19 + `.pre-commit-config.yaml`) | Keep as-is | Deterministic | Automated at commit-time and PR-time | — |
| Golden dataset evaluation | ✅ Built (deterministic metrics + structural judge 2026-06-23 + prose judge 2026-06-26) | Keep as-is | Hybrid | Metrics are math; narrative quality judged by `ProseQualityJudge` via `ClaudeProvider`; FR-28 fully closed | — |

---

## D. Missing Artifacts / Missing Controls

| Missing Item | Impact | Status |
|---|---|---|
| ~~`.claude/rules/` directory~~ | ~~Standards drift~~ | ✅ RESOLVED 2026-06-16 — 6 rules files created |
| ~~`tests/eval/` + `g2-g5/ideal.json`~~ | ~~Cannot validate beyond g1~~ | ✅ RESOLVED 2026-06-17 — all 5 oracles + eval harness built |
| CI/CD pipeline (GitHub Actions / similar) | No automated quality enforcement | ✅ RESOLVED 2026-06-19 — `.github/workflows/ci.yml` (Python 3.11+3.12 matrix) |
| Pre-commit hooks | Can commit broken code | ✅ RESOLVED 2026-06-19 — `.pre-commit-config.yaml` (4 local hooks) |
| `tests/eval/judge.py` | LLM narrative quality unscored | ✅ RESOLVED 2026-06-23 — `StructuralJudge` built (offline/CI-safe; structural score 1.00 on all 5 fixtures). ✅ RESOLVED 2026-06-26 — `ProseQualityJudge` built (`ProseQualityResponse`, `ClaudeProvider`, API-key guard; FR-28 fully closed). |
| `LocalLLMProvider` implementation | AI-first demo path is aspirational | ✅ RESOLVED 2026-06-18 — `src/rrr/providers/local_llm.py` (Ollama HTTP, 14 tests) |
| `MockLLMProvider` for demo / offline AI-first | Cannot demo AI reasoning without Ollama | ✅ RESOLVED 2026-06-20 — fixture-backed provider; full guardrail chain; `provider.type: mock_llm` |
| `Makefile` or `justfile` | No single command to run all checks | ✅ RESOLVED 2026-06-20 — `scripts/check_all.ps1` PowerShell gate wrapper |
| Integration test (end-to-end with assertions) | CLI tested manually, not programmatically | ✅ RESOLVED 2026-06-17 — `tests/eval/test_eval.py` calls `assess()` on all 5 fixtures |
| Telemetry / structured logging | No observability for provider calls | ✅ RESOLVED 2026-06-18 — W6: run-id + structured logging + per-assessor timing |
| Container / deployment artifacts | No cloud-native delivery story | ✅ RESOLVED 2026-06-20 — `Dockerfile` + `docker-compose.yml` + `docs/enterprise-deployment.md` |
| LangGraph orchestration wrapper | Self-assessment claimed LangGraph; code used ThreadPoolExecutor | ✅ RESOLVED 2026-06-20 — `src/rrr/orchestration/graph.py` thin StateGraph (ADR-0002 impl note) |

---

## E. Prioritized Remediation Plan

### Quick Wins (< 1 day each)
1. ✅ DONE 2026-06-19 — Move `langgraph` and `chromadb` to optional deps in `pyproject.toml`
2. ✅ DONE 2026-06-16 — Create `.claude/rules/` with pattern enforcement rules
3. ✅ DONE 2026-06-20 — `scripts/check_all.ps1` PowerShell gate wrapper
4. ✅ DONE 2026-06-19 — Add `.pre-commit-config.yaml` (4 local hooks: comment-coverage, ruff, mypy)
5. ✅ DONE 2026-06-17 — Author `g2-g5` `ideal.json` golden oracles

### Medium-Term (1-3 days each)
6. ✅ DONE 2026-06-18 — Implement `LocalLLMProvider` — stdlib urllib, Ollama HTTP on `127.0.0.1`, full guardrail chain, 14 tests
7. ✅ DONE 2026-06-17 — Implement deterministic eval metrics (`tests/eval/metrics.py`) — verdict accuracy 100%, macro-F1 1.000, score MAE 0
8. ✅ DONE 2026-06-19 — GitHub Actions CI workflow (`.github/workflows/ci.yml`, Python 3.11+3.12)
9. ✅ DONE 2026-06-17 — Integration tests: `test_eval.py` calls `assess()` on all 5 golden fixtures, asserts verdicts match `ideal.json`
10. ✅ DONE 2026-06-18 — Structured logging: W6 run-id + per-assessor timing + fallback warnings

### Strategic (3+ days)
11. ✅ DONE 2026-06-23/2026-06-26 — `StructuralJudge` + `EvalReportRenderer` built 2026-06-23; `ProseQualityJudge` + `ProseQualityResponse` built 2026-06-26 — live-LLM prose scoring via `ClaudeProvider`; eval report §4 added; FR-28 fully closed.
12. ✅ DONE 2026-06-19 — Chroma RAG built (optional 6D score-vector, `AssessmentStore(chroma_path=...)`, ADR-0007)
13. ✅ DONE 2026-06-19 — Jinja2 output layer (`MarkdownRenderer` + `PlanRenderer`, `rrr --format markdown/plan`, ADR-0002 impl noted)
14. ✅ RESOLVED 2026-06-30 — **ThreadPoolExecutor is the production mechanism; LangGraph is the optional tracing/visualization layer.** The workflow is a fixed fan-out/fan-in with no adaptive planning — ThreadPoolExecutor is correct and simpler. LangGraph stays as `rrr[graph]` optional dep for tracing/streaming/future branching. `Orchestrator.collect()` extracted so the LangGraph `collect_node` delegates to it — one code path, zero duplication (ADR-0002 impl-note 2026-06-30).

---

## F. Concrete Starter Artifacts

### Sample `.claude/rules/assessor-pattern.md`
```markdown
---
description: Enforce assessor implementation patterns
globs: ["src/rrr/assessors/*.py"]
---

When creating or modifying assessors:
- Every assessor MUST extend `BaseAssessor`
- The `_assess()` method MUST return `DeterministicAssessment` — never call the provider directly
- The score MUST be computed from deterministic math, never from provider output
- All tool calls MUST go through `self.invoke_tool()` for recording
- Add unit tests in `tests/unit/test_<dimension>_assessor.py` verified against golden fixtures
- Run `pytest tests/unit/test_<dimension>_assessor.py` before considering the work complete
```

### Sample `.claude/rules/model-conventions.md`
```markdown
---
description: Enforce data model conventions
globs: ["src/rrr/models/*.py"]
---

When creating or modifying models:
- All models MUST extend `RRRModel` (which extends `BaseModel` with project defaults)
- All fields MUST have type annotations and `Field()` with description
- Use `model_validator` for cross-field constraints
- Enums go in `models/enums.py`
- Run `mypy src` after any model change — strict typing is required (NFR-5)
```

### Sample Makefile
```makefile
.PHONY: lint type test check all

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy src

test:
	pytest

check: lint type test

all: check
```

### Sample Eval Suite Structure
```
tests/eval/
├── __init__.py
├── metrics.py          # Deterministic: verdict accuracy, risk F1, score MAE
├── judge.py            # LLM-as-judge: narrative quality scoring (offline)
├── run_eval.py         # Entry point: run all golden fixtures, compute all metrics
└── report.py           # Generate Markdown eval report
```

### Sample Workflow Classification Map
```
┌─────────────────────────────────────────────────────────┐
│             RRR AI Architecture Map                       │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  DETERMINISTIC (code, always)                            │
│  ├── Config loading + validation                         │
│  ├── Tool invocation + timeout + recording               │
│  ├── Numeric scoring (all 5 dimensions)                  │
│  ├── Risk factor extraction (threshold-based)            │
│  ├── Weight redistribution                               │
│  ├── Verdict derivation (score → band → gates)           │
│  ├── Output validation (Pydantic guardrail)              │
│  ├── Persistence (SQLite)                                │
│  └── Trend computation                                   │
│                                                           │
│  SINGLE LLM CALL (provider, justified)                   │
│  ├── Dimension narrative (per assessor, 5× parallel)     │
│  ├── Verdict rationale synthesis (1× post-scoring)       │
│  ├── Remediation plan (1× post-scoring)                  │
│  └── LLM-as-judge eval (offline, not in hot path)        │
│                                                           │
│  PARALLELIZATION (orchestrator)                          │
│  └── 5 assessors fan-out / fan-in (ThreadPoolExecutor)   │
│      (Each assessor = deterministic + 1 LLM call)        │
│                                                           │
│  NOT USED (correctly)                                    │
│  ├── No prompt chaining                                  │
│  ├── No multi-step agent loops                           │
│  ├── No autonomous decision-making                       │
│  └── No open-ended exploration                           │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Section-Specific Deep Dives

### SECTION 3 — AI/Agentic Architecture Review

| Use Case | Pattern | Verdict |
|---|---|---|
| Dimension reasoning (narrative) | Single LLM call | Correct. No chaining needed — facts in, prose out |
| Verdict synthesis | Single LLM call | Correct. One call, cross-dimension, schema-validated |
| Assessor orchestration | Parallelization (fan-out/fan-in) | Correct. Fixed 5 workers, no routing needed, no state between them |
| RAG historical context (planned) | Single LLM call with retrieval | Correct pattern when implemented. Not agentic — retrieve then generate |
| LLM-as-judge eval | Single LLM call | Correct. Score against ideal, no iteration |

**No multi-step agentic behavior is needed.** The system's workflow is fully predictable: ingest → score × 5 → fuse → verdict → persist. There is zero open-ended exploration or adaptive planning. The `ThreadPoolExecutor` is the correct orchestration mechanism — simpler than LangGraph and sufficient for fixed fan-out/fan-in. Consider keeping LangGraph as optional for visualization/tracing only.

### SECTION 4 — Prompt/Context Review

**Prompts found:** The `ReasoningRequest` envelope (providers/base.py) IS the prompt structure — it separates instruction from data cleanly. The `RuleBasedProvider` doesn't use prompts at all (it's templated). The `LocalLLMProvider` and `ClaudeProvider` (✅ both built — 2026-06-18 and 2026-06-25 respectively) use `ReasoningRequest` fields as the prompt payload.

**Evaluation:**
- Clarity: High — `summary`, `facts`, `risk_factors`, `allowed_classifications` are explicit
- Output specificity: High — response must match a Pydantic schema exactly
- Injection safety: Good — `facts` are data, never instructions
- Missing: No actual prompt templates for the LLM providers exist yet (since they're not implemented)

**CLAUDE.md / project-context.md:**
- Excellent context engineering — persona, constraints, decision process, output format all specified
- The "8-section format" for significant responses is good structure
- The "principal architect first, engineer second" framing is correct for this project
- Custom commands (`/adr`, `/check`, `/plan-feature`) codify workflows as deterministic entry points

### SECTION 5 — Claude Code Operating Context

| Artifact | Present? | Quality |
|---|---|---|
| `CLAUDE.md` | Yes | Excellent — concise, high-signal, links to durable docs |
| `.claude/project-context.md` | Yes | Good — persona + rules + output format |
| `.claude/settings.json` | Yes | Good — permissions scoped, env configured |
| `.claude/commands/` | Yes (3) | Good — `adr`, `check`, `plan-feature` |
| `.claude/skills/` | Empty | Gap — no reusable skill definitions |
| `.claude/rules/` | ✅ Present (2026-06-16) | 6 files: assessor-pattern, model-conventions, provider-pattern, deterministic-first, adr-lifecycle, test-coverage |
| Directory-level CLAUDE.md | None | Minor gap — could help for `tests/` or `src/rrr/providers/` |

**The repo is well-optimized for Claude Code.** The CLAUDE.md is among the best I've seen — it's concise, links to authoritative docs instead of duplicating, states hard constraints, and provides the project structure. The custom commands codify common workflows. The permissions model is appropriately scoped.

### SECTION 6 — Tool/Integration Review

| Tool | Scoped? | Typed? | Safe to retry? | Structured output? |
|---|---|---|---|---|
| `RKTBrainReader` | Yes (reads brain JSON) | Yes (Pydantic models) | Yes (read-only) | Yes |
| `EnvironmentSourceReader` | Yes (file/API) | Yes | Yes (read-only) | Yes |
| `DependencySourceReader` | Yes (file/API) | Yes | Yes (read-only) | Yes |
| `ToolRunner` | Yes (timeout + recording) | Yes (Protocol) | N/A (wrapper) | Yes (ToolInvocationModel) |
| `AssessmentStore` | Yes (SQLite) | Yes | Yes (retry built-in) | Yes |

All tools follow the `BaseTool` Protocol, are narrowly scoped, return typed outputs, and are safe to retry. The separation between read-only data tools and the side-effecting persistence layer is clean. No tool mixes read and write operations.

### SECTION 7 — Testing & Reliability

| Category | Status | Quality |
|---|---|---|
| Unit tests | 14 files, 112 tests | Good coverage of individual components |
| Property tests | 6 properties via Hypothesis | Excellent — guards scoring invariants |
| Golden fixtures | ✅ All 5 `ideal.json` authored (2026-06-17) | g1–g5 fully curated oracles |
| Eval harness | ✅ Built 2026-06-17 (`tests/eval/`) | 13 tests; accuracy 100%, macro-F1 1.000 |
| Integration tests | ✅ `test_eval.py` calls `assess()` on all 5 fixtures | asserts verdicts match `ideal.json` |
| Retry logic | Persistence retry (3×/5s) | Good |
| Fallback logic | Provider → RuleBasedProvider | Excellent |
| Structured output validation | Pydantic on every boundary | Excellent |
| Error taxonomy | `RRRError` hierarchy | Good |

### SECTION 8 — Security & Governance

- **Injection safety:** Correctly mitigated via `ReasoningRequest` data/instruction separation
- **Local-first enforcement:** Runtime-enforced in `pipeline.py` — non-local rejected with error
- **Allowed hosts:** Configurable whitelist (`127.0.0.1`/`localhost` default)
- **Secrets:** No API keys in Phase 1; Phase 2 Claude provider would need key management (not yet relevant)
- **Blast radius:** A bad LLM output affects only narrative/remediation, never score/verdict
- **Human review:** Verdict is advisory — a human makes the final release decision

### SECTION 9 — Cost & Efficiency

**Phase 1 cost: Zero LLM tokens.** The `RuleBasedProvider` uses no model. This is the ideal default for CI and deterministic testing.

**Phase 2 cost model (when implemented):**
- 5 assessor calls (parallel, small prompts) + 1 verdict synthesis = 6 LLM calls per assessment
- Each call has bounded input (structured `ReasoningRequest`) and bounded output (Pydantic schema)
- No context stuffing — facts are pre-computed and minimal
- No retrieval-augmented generation yet (Chroma is M4)
- The architecture is already optimized for minimum token usage

**Recommendation:** When `LocalLLMProvider` lands, route dimension reasoning to the local model (cheap/fast) and reserve Claude for the verdict synthesis only (higher quality needed for the cross-dimension judgment). This is a natural routing pattern the existing interface supports.

---

## Final Assessment

This project demonstrates **Senior RDE-level AI engineering**. The architecture correctly identifies where AI adds value (judgment, synthesis, narrative) and where it doesn't (scoring, validation, orchestration). The deterministic-first principle is not just documented — it's enforced in code. The Claude Code developer experience is well-engineered with CLAUDE.md, custom commands, and permissions.

The primary gaps are operational: no CI/CD, incomplete eval harness, and unimplemented provider alternatives. These are execution items, not design flaws. The architecture is sound and ready for those additions without restructuring.
