# Orchestration — layer orientation

The deterministic-first invariant is always loaded via `.claude/rules/deterministic-first.md`.
This file adds orientation specific to this layer — see the rules file for the full constraint table.

## Scoring pipeline
`_fan_out()` → `weighted_score()` → `derive_verdict()` → verdict synthesis — all pure deterministic code.
No LLM output may enter `weighted_score()` or `derive_verdict()`.

## Key files
- `orchestrator.py` — `_fan_out()` parallel execution + `Orchestrator.run()` + `collect()` (public, used by both `run()` and the LangGraph `collect_node`)
- `graph.py` — LangGraph two-node StateGraph wrapper (`dispatch` → `collect`, ADR-0002 ✅); `collect_node` delegates to `orchestrator.collect()` — no duplication
- `scoring.py` — `weighted_score()` with weight redistribution for unavailable dimensions (ADR-0005)
- `verdict.py` — `derive_verdict()`: score band → verdict label + gate application
- `gate_engine.py` — caps verdict from CRITICAL/MAJOR risk factors (ADR-0013/0014)
- `trends.py` — delta computation vs. previous run (FR-9)

## LangGraph entry point
`run_assessment_graph()` in `graph.py` is the public entry point called from `pipeline.py`.
Falls back to `Orchestrator.run()` transparently if `langgraph` is not installed.
ThreadPoolExecutor stays inside the `dispatch` node — do not move thread management to the graph layer.

**Architectural position (2026-06-30):** ThreadPoolExecutor is the production mechanism. LangGraph is
the optional tracing/visualization layer — correct for this fixed fan-out/fan-in workflow with no
adaptive planning. Architecture-review item 14 closed.

## Gate engine rule
All verdict caps live in `gate_engine.py` only — never in assessors, graph nodes, or providers.

## ADR guard
Any change to scoring algorithm, weight structure, or gate logic requires a new ADR or an
impl-note on an existing one. Run `scripts/check_alignment.py` after to verify the count.
