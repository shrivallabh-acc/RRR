# ADR 0002: LangGraph for Agent Orchestration

- **Status:** Accepted (implemented 2026-06-20)
- **Date:** 2026-06-08

## Context
RRR runs 5 specialized assessor agents that must execute in parallel (fan-out),
have their results collected (fan-in), and tolerate individual failures. We need an
orchestration layer that models this graph of agents and their result aggregation.

## Decision
Use **LangGraph** to model the orchestrator as a graph: a dispatch node fans out to
the 5 assessor nodes in parallel, and a collector node fans in their `DimensionResult`s
for scoring and verdict derivation.

## Consequences
- Parallel execution and result aggregation are first-class in the graph model.
- Graceful degradation (weight redistribution) is handled at the fan-in node.
- Adds LangGraph as a dependency; assessors stay decoupled behind `BaseAssessor`.

## Implementation status (M3) — deferred
The decision stands as the **target**, but the M3 orchestrator implements the fan-out/fan-in with
`concurrent.futures.ThreadPoolExecutor` instead of LangGraph (not yet installed; native-build risk
on Python 3.14; avoids a heavy dependency before it earns its place). The scoring, weight
redistribution, gate, and verdict logic live in framework-independent functions
(`orchestration/scoring.py`, `verdict.py`), so LangGraph can wrap the existing engine later with no
change to that logic. Re-evaluate when the graph gains real branching/streaming needs.

## Implementation note (2026-06-20) — LangGraph wrapper built
`src/rrr/orchestration/graph.py` implements the two-node `StateGraph` (`dispatch` → `collect`).
`dispatch` calls `Orchestrator._fan_out()` (ThreadPoolExecutor stays inside this node for Python 3.14
compatibility); `collect` runs scoring, gate evaluation, and synthesis. `pipeline.assess()` now calls
`run_assessment_graph()` instead of `Orchestrator.run()` directly. When `langgraph` is not installed
the function falls back to `Orchestrator.run()` transparently — no behavior change for existing users.
Install with `pip install "rrr[graph]"`. The scoring/verdict engine in `scoring.py` and `verdict.py`
was unchanged, confirming the framework-independence property stated in the original decision.

## Implementation note (2026-06-30) — Architectural position clarified; collect_node refactored

**ThreadPoolExecutor is the production execution mechanism.** LangGraph is the optional
tracing/visualization layer. The workflow is fully predictable (ingest → score × N → fuse → verdict
→ persist) with no open-ended exploration or adaptive planning — ThreadPoolExecutor is the correct
mechanism and simpler than a full graph runtime for this fixed fan-out/fan-in pattern. This closes
architecture-review item 14.

**`Orchestrator.collect()` extracted** — previously `_run_via_graph`'s `collect_node` duplicated
~80 lines of `Orchestrator.run()` while accessing private members (`_provider`, `_weights()`,
`_config`). `Orchestrator.collect(results, *, release, value_stream)` is now a public method that
owns the scoring → verdict → synthesis → output-building pipeline. `run()` calls `_fan_out()` +
`collect()`. The LangGraph `collect_node` now delegates to `orchestrator.collect()` — one code path,
no duplication, impossible to diverge. All 6 graph tests + full suite pass unchanged.
