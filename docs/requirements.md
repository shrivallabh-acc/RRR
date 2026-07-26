# Requirements — Release Readiness Results (RRR)

## Functional Requirements

### Assessment Dimensions
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | **Scope** assessor reads the latest brain snapshot's per-release `summary` (total/closed/remaining/pct); completion = `closed/total`; classifies the release Delivered (≥90%), Partially Delivered (≥50%), Not Delivered (<50%); uses `weekly_last3` as velocity context; score = completion ratio. (Release-level; per-capability breakdown is not in the brain extract — ADR-0012) | Must |
| FR-2 | **Estimation** assessor reads `pv_latest {planned, actual}` (latest earned-value point); variance% `((actual-planned)/planned)×100`; classifies over (< -10%), under (> +10%), within-tolerance (±10%); score = `max(0, 100-\|variance%\|)/100`. (Brain pre-reduces PV to the latest point, so MAPE = \|variance\|; the per-item / 3+-consecutive-run model does not apply — ADR-0012) | Must |
| FR-3 | **Environment** assessor accepts file (JSON/CSV) or live API; scores components by provisioning status validated(1.0)/configured(0.75)/provisioned(0.5)/missing(0.0); gap severity by stability down=critical, degraded=major, stable=minor; score = avg(component scores); 10s source timeout | Must |
| FR-4 | **Test Readiness** assessor uses three weighted sub-components from brain data: Quality (0.4 = `sq_avg`/3, 0–3 scale; flags `sq_below_1`), Defect trend (0.3 = direction of `defect_trend_last5`, declining→1.0/flat→0.5/rising→0.0; `defects_open.by_severity` blocker/critical as risks), E2E pass rate (0.3 = `e2e_latest.passed/(passed+failed)`). When `e2e_latest` is absent, drop E2E and renormalize quality/defect weights (0.4/0.3→0.571/0.429) with reduced confidence — ADR-0012 | Must |
| FR-5 | **Dependency** assessor accepts file or live API; score = (complete AND passed)/total; classifies blocking (not-started OR failed), at-risk (in-progress AND not-validated), on-track (otherwise) | Must |

### Orchestration & Verdict
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6 | Orchestrator dispatches all 5 assessors **in parallel** (fan-out) and collects results (fan-in) | Must |
| FR-7 | Score = weighted sum of dimension scores; weight of unavailable dimensions redistributed equally among available; risk acceptance adjusts scores proportionally | Must |
| FR-8 | Verdict mapping: INCOMPLETE (< `minimum_assessors` succeeded), else band from score GO (≥0.8), NO_GO (<0.4), CONDITIONAL (between), **then veto/cap gates ceiling the verdict** — final = most restrictive of band and all triggered caps (GO>CONDITIONAL>NO_GO); each gate recorded as a risk factor (ADR-0013) | Must |
| FR-9 | Compute per-dimension trends vs previous assessment: Δ>0.05 improving, Δ<-0.05 degrading, else stable | Should |

### Tooling & Evidence
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-10 | All tools implement `BaseTool` protocol (`name` property + `invoke(**params)`); new tools addable without modifying assessors | Must |
| FR-11 | `ToolRunner` enforces timeout (threading, default 30s) and records `ToolInvocationModel` (name, params, output_summary ≤500 chars, success, duration_ms, error_reason); raises `ToolTimeoutError` / `ToolInvocationError` | Must |
| FR-12 | `BaseAssessor` ABC provides `invoke_tool()`, `calculate_confidence()` (all pass→1.0, any fail→0.5 cap, all fail→0.0 + INCOMPLETE), `build_evidence()`, `reset()` | Must |
| FR-13 | Each assessor produces a `DimensionResult` (score 0.0–1.0 + confidence + evidence + risk factors) | Must |

### Persistence & Config
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-14 | Every assessment persists to SQLite for historical/trend comparison; retry persist (default 3 attempts, 5s interval) | Must |
| FR-15 | `ConfigLoader` loads YAML → merges defaults → validates via Pydantic; raises `ConfigurationError` with detailed error list; weights must sum to 1.0 | Must |

### AI Reasoning, Memory & Guardrails
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-21 | Each assessor delegates judgment to an **`LLMProvider`** (`reason(prompt, schema)`) to classify ambiguous items, extract risk factors, and write the evidence narrative — while the numeric score stays deterministic | Must |
| FR-22 | The orchestrator uses the provider to synthesize the **verdict rationale** and a cross-dimension **remediation plan**; the verdict *label* is derived from the deterministic score, not provider text | Must |
| FR-23 | Every provider call returns **Pydantic-validated structured output**; on validation failure or refusal, **one repair retry**, else fall back to `RuleBasedProvider` + reduced confidence | Must |
| FR-24 | Persist an embedded summary of each assessment to a **local Chroma** vector store (local embeddings); at verdict time **RAG-retrieve** the most similar prior releases to ground trend/benchmark context | Must |
| FR-25 | Record provider, prompt, and (where applicable) token usage into the audit trail; ingested data is treated as **data, not instructions** (injection safety); system prompt fixed | Should |
| FR-30 | Ship **three providers** behind one interface: `RuleBasedProvider` (default, no model), `LocalLLMProvider` (Ollama/llama.cpp on `127.0.0.1`), `ClaudeProvider` (Phase 2 external). Selection via config | Must |

### Evaluation
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-26 | Maintain a **golden dataset** of 3–5 release fixtures, each with a manually-written ideal verdict, risk factors, and remediation (`tests/golden/`) | Must |
| FR-27 | Compute verdict **accuracy + macro-F1**, risk-factor **F1**, remediation **completeness**, and per-dimension score MAE against the golden set | Must |
| FR-28 | Provide one **automated evaluation** — an **LLM-as-judge** scoring narrative/remediation on faithfulness, completeness, actionability (offline, may use a cheaper model) | Must |
| FR-29 | Keep **Hypothesis** property tests for scoring invariants and determinism (in addition to the eval harness) | Should |

### CLI & Output
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-16 | Click-based CLI emits `"VERDICT: GO  SCORE: 84"`, or full JSON with `--verbose` | Must |
| FR-17 | Exit codes: 0=GO, 1=NO-GO, 2=CONDITIONAL, 3=ERROR | Must |
| FR-18 | Emit versioned `AssessmentOutputModel` (schema_version "1.0.0"): dimensions, trend_data, progress highlights, benchmark, audit_trail | Must |
| FR-19 | Render Markdown readiness plans & checklists via Jinja2 (M2 / RRP) | Should |
| FR-20 | Web dashboard (NiceGUI) — Phase 2 / M5 (opt-in, `pip install rrr[ui]`) — ✅ built 2026-06-26 (ADR-0020) | Could |

## Non-Functional Requirements
| ID | Category | Target |
|----|----------|--------|
| NFR-1 | Performance | Parallel assessor execution; assessor timeout 300s default / 60s environment; tool timeout 30s default |
| NFR-2 | Reliability | Graceful degradation — verdict produced if ≥`minimum_assessors` (3) succeed; no total failure |
| NFR-3 | Auditability | Navigable chain of evidence for every conclusion; ISO 8601 timestamps with millisecond precision |
| NFR-4 | Portability | Zero-config, file-based SQLite; runs on Python 3.11+ |
| NFR-5 | Data quality | All models Pydantic v2 with `Field` + `model_validator`; type hints on all public functions |
| NFR-6 | Testability | Property-based tests (Hypothesis) for scoring invariants; pytest suite |
| NFR-7 | Maintainability | Modular tools, ABC-based assessors; new dimensions/tools added without core changes |
| NFR-8 | **Local-first / no external** | Phase 1 makes **no external network calls** at runtime; a fresh checkout runs offline; non-local endpoints rejected unless explicitly allowlisted (`127.0.0.1`/`localhost`). External providers/sources are Phase-2 opt-in (ADR-0010) |
| NFR-9 | Portability of AI path | System runs with **no model required** (`RuleBasedProvider`); local LLM is opt-in and pulled once at setup, not a runtime network dependency |

## Constraints & Assumptions
- **Local-first (hard constraint):** Phase 1 runs entirely on the user's machine with no
  external calls; everything required is local (ADR-0010).
- Python 3.11+; pluggable **`LLMProvider`** (default `RuleBasedProvider`, no model);
  **Chroma** (embedded) for vector memory/RAG with local embeddings; LangGraph; Pydantic v2;
  Click; SQLite; Jinja2; YAML config; Hypothesis + pytest.
- Optional local LLM (`LocalLLMProvider`) via **Ollama / llama.cpp** on `127.0.0.1`; weights
  pulled once at setup. No API key needed in Phase 1.
- Environment & Dependency data come from **local files (JSON/CSV) or localhost (127.0.0.1)
  mock APIs**; live external APIs are Phase-2 opt-in.
- Phase 2 external scale: `ClaudeProvider` (`anthropic` SDK, `claude-sonnet-4-6` default, `pip install rrr[cloud]`) behind the same interface; requires `ANTHROPIC_API_KEY` only then. ✅ Built 2026-06-25.
- Upstream `brain/*.json` snapshots from RKT Program Metrics are available and well-formed.
- Estimation requires ≥3 items; otherwise the dimension is not scored.
- Data interchange: YAML for config, JSON for data, Markdown for human-readable output.

## Out of Scope
- Collecting or editing source program metrics (owned by RKT Program Metrics).
- Real-time monitoring, notifications, or automated release execution.
- Authentication / multi-tenant access control (single-user CLI for initial release).
