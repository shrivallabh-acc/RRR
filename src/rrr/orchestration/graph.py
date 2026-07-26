"""LangGraph StateGraph wrapper for the RRR assessment pipeline (ADR-0002).

**Architectural position (2026-06-30):** ``ThreadPoolExecutor`` inside
``Orchestrator._fan_out()`` is the production execution mechanism — it is simple,
Python-3.14-compatible, and sufficient for the fixed fan-out/fan-in workflow.
LangGraph is the *optional tracing and visualization layer*: when installed it
wraps the same ``Orchestrator`` in a two-node ``StateGraph`` (``dispatch`` →
``collect``) that enables graph-native tracing, streaming, and future branching
without changing any deterministic logic. Install with ``pip install "rrr[graph]"``.

The ``collect`` node delegates to ``Orchestrator.collect()`` so scoring,
gate evaluation, and synthesis always run through exactly one code path.
"""

from __future__ import annotations

import logging
from typing import Any

from rrr.assessors.base import BaseAssessor
from rrr.config.schema import RRRConfig
from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import ReleaseRiskTier
from rrr.orchestration.orchestrator import Orchestrator
from rrr.providers.base import LLMProvider

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]

    _LANGGRAPH_AVAILABLE = True
except ImportError:  # langgraph optional dep — graceful fallback (ADR-0002)
    _LANGGRAPH_AVAILABLE = False
    logger.debug("langgraph not installed — run_assessment_graph() will use Orchestrator directly")


def run_assessment_graph(
    config: RRRConfig,
    assessors: list[BaseAssessor],
    *,
    release: str,
    value_stream: str = "",
    provider: LLMProvider | None = None,
    tier: ReleaseRiskTier | None = None,
) -> AssessmentOutputModel:
    """Run the assessment pipeline, optionally via a LangGraph StateGraph.

    When ``langgraph`` is installed, wraps the existing ``Orchestrator`` in a
    two-node ``StateGraph`` (``dispatch`` → ``collect``) that enables tracing and
    visualization. When ``langgraph`` is absent, delegates directly to
    ``Orchestrator.run()`` — the result is identical.

    :param config: Validated RRRConfig driving weights, gates, timeouts.
    :param assessors: ``BaseAssessor`` instances, already fully constructed.
    :param release: Release identifier (IR name) for the audit trail.
    :param value_stream: Optional value-stream label; defaults to empty string.
    :param provider: ``LLMProvider`` to use; if None the orchestrator builds one
        from ``config`` (this parameter exists for testability).
    :param tier: Optional release risk tier (ADR-0016 items 4-5). When supplied,
        the matching ``TierThresholds`` from ``config.tiers`` override the global
        thresholds for verdict derivation.
    """
    if provider is None:
        from rrr.pipeline import build_provider

        provider = build_provider(config)

    orchestrator = Orchestrator(config, provider)

    if not _LANGGRAPH_AVAILABLE:
        logger.debug("run_assessment_graph: langgraph absent — using Orchestrator directly")
        return orchestrator.run(assessors, release=release, value_stream=value_stream, tier=tier)

    return _run_via_graph(
        orchestrator, assessors, release=release, value_stream=value_stream, tier=tier
    )


def _run_via_graph(
    orchestrator: Orchestrator,
    assessors: list[BaseAssessor],
    *,
    release: str,
    value_stream: str,
    tier: ReleaseRiskTier | None = None,
) -> AssessmentOutputModel:
    """Build and invoke a two-node StateGraph wrapping the existing Orchestrator.

    The graph has two nodes:
    - ``dispatch``: calls ``Orchestrator._fan_out()`` in parallel; stores results
      in graph state.
    - ``collect``: calls ``Orchestrator.collect()`` on the pre-computed fan-out
      results — scoring, gate evaluation, synthesis, and output construction all
      run through the single authoritative code path (no duplication).
    """
    from typing import TypedDict

    from rrr.models.dimension import DimensionResult

    class _State(TypedDict):
        """State passed between LangGraph nodes."""

        fan_out_results: list[DimensionResult]
        release: str
        value_stream: str
        tier: ReleaseRiskTier | None
        result: AssessmentOutputModel | None

    def dispatch_node(state: _State) -> dict[str, Any]:
        """Fan out all assessors in parallel and store their DimensionResults."""
        results = orchestrator._fan_out(assessors)
        return {"fan_out_results": results}

    def collect_node(state: _State) -> dict[str, Any]:
        """Score, apply gates, synthesize verdict from pre-computed fan-out results."""
        result = orchestrator.collect(
            state["fan_out_results"],
            release=state["release"],
            value_stream=state["value_stream"],
            tier=state["tier"],
        )
        return {"result": result}

    # Build the two-node graph: START → dispatch → collect → END
    graph = StateGraph(_State)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("collect", collect_node)
    graph.add_edge(START, "dispatch")
    graph.add_edge("dispatch", "collect")
    graph.add_edge("collect", END)

    app = graph.compile()
    initial: _State = {
        "fan_out_results": [],
        "release": release,
        "value_stream": value_stream,
        "tier": tier,
        "result": None,
    }
    final_state: _State = app.invoke(initial)
    result = final_state.get("result")
    if result is None:
        # Should never happen — collect_node always sets result.
        raise RuntimeError("LangGraph collect_node did not produce a result")
    return result
