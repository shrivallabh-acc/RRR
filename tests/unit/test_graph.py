"""Tests for src/rrr/orchestration/graph.py — LangGraph StateGraph wrapper (ADR-0002)."""

from __future__ import annotations

from pathlib import Path

from rrr.config import ConfigLoader
from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import Verdict
from rrr.orchestration import run_assessment_graph
from rrr.orchestration.graph import _LANGGRAPH_AVAILABLE
from rrr.providers import RuleBasedProvider

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1 = GOLDEN / "g1_clean_release"
VS = "Retirement-Services"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_G1_IR = "Launch 36 - Unified Onboarding"


def _build_assessors(fixture_dir: Path, config=None, ir_name: str = _G1_IR):
    """Build all five assessors pointing at the given golden fixture inputs."""
    from rrr.assessors import (
        DependencyAssessor,
        EnvironmentAssessor,
        EstimationAssessor,
        ScopeAssessor,
        TestReadinessAssessor,
    )
    from rrr.tools import (
        DependencySourceReader,
        EnvironmentSourceReader,
        RKTBrainReader,
        ToolRunner,
    )

    cfg = config or ConfigLoader.load()
    runner = ToolRunner(
        default_timeout=float(cfg.timeouts.tool_default),
        retry_count=0,
        retry_backoff_s=0.0,
    )
    brain_dir = fixture_dir / "inputs" / "brain"
    env_path = fixture_dir / "inputs" / "environment.json"
    dep_path = fixture_dir / "inputs" / "dependency.json"

    brain = RKTBrainReader(str(brain_dir))
    env_reader = EnvironmentSourceReader(path=str(env_path))
    dep_reader = DependencySourceReader(path=str(dep_path))
    provider = RuleBasedProvider()

    tr_weights = cfg.assessors.test_readiness.weights
    return [
        ScopeAssessor(
            runner,
            provider,
            brain,
            value_stream=VS,
            ir_name=ir_name,
            snapshot="latest",
            scope_creep_threshold=cfg.gates.scope_creep_threshold,
        ),
        EstimationAssessor(
            runner, provider, brain, value_stream=VS, ir_name=ir_name, snapshot="latest"
        ),
        TestReadinessAssessor(
            runner,
            provider,
            brain,
            value_stream=VS,
            ir_name=ir_name,
            snapshot="latest",
            quality_weight=tr_weights["quality"],
            defect_weight=tr_weights["defect_trend"],
            e2e_weight=tr_weights["e2e_pass_rate"],
            e2e_critical_floor=cfg.gates.e2e_critical_floor,
            freshness_max_age_days=cfg.assessors.test_readiness.freshness_max_age_days,
        ),
        EnvironmentAssessor(runner, provider, env_reader),
        DependencyAssessor(runner, provider, dep_reader),
    ]


# ---------------------------------------------------------------------------
# run_assessment_graph returns a valid AssessmentOutputModel
# ---------------------------------------------------------------------------


def test_run_assessment_graph_returns_output_model():
    """run_assessment_graph should return a typed AssessmentOutputModel."""
    cfg = ConfigLoader.load()
    assessors = _build_assessors(G1, cfg)
    provider = RuleBasedProvider()
    result = run_assessment_graph(
        cfg, assessors, release="test-run", value_stream=VS, provider=provider
    )
    assert isinstance(result, AssessmentOutputModel)


def test_run_assessment_graph_g1_is_go():
    """g1_clean_release should produce a GO verdict through run_assessment_graph."""
    cfg = ConfigLoader.load()
    assessors = _build_assessors(G1, cfg)
    provider = RuleBasedProvider()
    result = run_assessment_graph(
        cfg,
        assessors,
        release="Launch 36 - Unified Onboarding",
        value_stream=VS,
        provider=provider,
    )
    assert result.verdict == Verdict.GO


def test_run_assessment_graph_score_in_range():
    """Score from run_assessment_graph must be in [0, 100]."""
    cfg = ConfigLoader.load()
    assessors = _build_assessors(G1, cfg)
    provider = RuleBasedProvider()
    result = run_assessment_graph(
        cfg, assessors, release="test-run", value_stream=VS, provider=provider
    )
    assert 0 <= result.score <= 100


def test_run_assessment_graph_has_five_dimensions():
    """All five dimensions should be present in the output."""
    cfg = ConfigLoader.load()
    assessors = _build_assessors(G1, cfg)
    provider = RuleBasedProvider()
    result = run_assessment_graph(
        cfg, assessors, release="test-run", value_stream=VS, provider=provider
    )
    assert len(result.dimensions) == 5


# ---------------------------------------------------------------------------
# Fallback parity: run_assessment_graph == Orchestrator.run() on same inputs
# ---------------------------------------------------------------------------


def test_graph_and_orchestrator_produce_same_verdict():
    """The graph wrapper must produce the same verdict as Orchestrator.run() for g1."""
    from rrr.orchestration import Orchestrator

    cfg = ConfigLoader.load()
    provider = RuleBasedProvider()

    assessors_graph = _build_assessors(G1, cfg)
    assessors_orch = _build_assessors(G1, cfg)

    graph_result = run_assessment_graph(
        cfg, assessors_graph, release="test", value_stream=VS, provider=provider
    )
    orch_result = Orchestrator(cfg, provider).run(assessors_orch, release="test", value_stream=VS)

    assert graph_result.verdict == orch_result.verdict
    assert graph_result.score == orch_result.score


# ---------------------------------------------------------------------------
# LANGGRAPH_AVAILABLE flag is a bool
# ---------------------------------------------------------------------------


def test_langgraph_available_is_bool():
    """_LANGGRAPH_AVAILABLE must be a bool (not None, not a module)."""
    assert isinstance(_LANGGRAPH_AVAILABLE, bool)
