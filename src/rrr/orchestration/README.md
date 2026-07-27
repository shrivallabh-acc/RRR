# Orchestration

The orchestration layer fans out to all configured assessors in parallel, collects
`DimensionResult` objects, computes the weighted score and verdict, and synthesises the
final `AssessmentOutputModel`.

---

## Module overview

| File | Purpose |
|---|---|
| `orchestrator.py` | `Orchestrator` — fan-out via `ThreadPoolExecutor`, collect, score, verdict |
| `scoring.py` | `score_dimensions()`, `split_scores()`, `redistribute_weights()` |
| `verdict.py` | `derive_verdict()`, `triggered_caps()`, `score_band()` |
| `gates.py` | `GateEngine` — maps risk factor severity + config gates to verdict caps |
| `trends.py` | `compute_trends()` — delta + direction vs previous assessment |
| `graph.py` | Optional LangGraph `StateGraph` wrapper (tracing/visualisation layer) |
| `__init__.py` | Public re-exports |

---

## Execution model

```
Orchestrator.assess(release, config)
  │
  ├─ Orchestrator.collect()      ← builds assessor list from config
  │    └─ ThreadPoolExecutor     ← all assessors run in parallel
  │         └─ assessor.assess() ← _assess() then reason() per assessor
  │
  ├─ score_dimensions()          ← weighted average with redistribution
  ├─ split_scores()              ← ship_safety + delivery_performance sub-scores
  ├─ triggered_caps()            ← gate engine: CRITICAL → NO_GO, MAJOR → CONDITIONAL
  ├─ derive_verdict()            ← bands + caps → final label
  ├─ provider.reason(request)    ← ONE LLM call: rationale + remediation
  └─ AssessmentOutputModel(...)  ← typed result
```

---

## Scoring

`score_dimensions()` computes the weighted mean across available dimensions. If a
dimension is `unavailable` (timeout, missing data, error), its weight is redistributed
proportionally across the remaining available dimensions — the score stays comparable
(ADR-0005).

`split_scores()` partitions dimensions into two groups:
- **ship_safety**: test_readiness, environment, dependency, operability, observability
- **delivery_performance**: scope, estimation

Each group is scored independently and attached to `AssessmentOutputModel`.

---

## Verdict derivation (in priority order)

1. Available dimensions < `minimum_assessors` → **INCOMPLETE**
2. CRITICAL risk factor exists → **NO_GO** (gate cap)
3. MAJOR risk factor exists → at most **CONDITIONAL** (gate cap)
4. Required dimension missing/unavailable → at most **CONDITIONAL**
5. Aggregate confidence < `confidence_floor` → at most **CONDITIONAL**
6. Score ≥ `go` threshold → **GO**; score < `no_go` threshold → **NO_GO**; otherwise → **CONDITIONAL**

---

## LangGraph (optional)

`graph.py` wraps the same `Orchestrator.collect()` call inside a LangGraph
`StateGraph` for visualisation and tracing. It is an **optional layer** — the production
mechanism is `ThreadPoolExecutor`. Enable with `pip install "rrr[graph]"`.

The graph exposes the same interface as `Orchestrator` and can be swapped in via config
without changing any other code.

---

## Single-LLM-call ceiling (ADR-0017)

- Each assessor makes exactly **one** provider call (dimension narrative).
- The orchestrator makes exactly **one** provider call (verdict rationale + remediation).
- No prompt chaining, multi-turn loops, or agent iteration. Any change to this
  constraint requires a new ADR.
