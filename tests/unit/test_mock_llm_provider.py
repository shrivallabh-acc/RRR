"""Tests for MockLLMProvider — fixture-backed demo provider (Phase 1)."""

from __future__ import annotations

from pathlib import Path

from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.llm import DimensionReasoning, VerdictSynthesis
from rrr.providers.base import ReasoningRequest
from rrr.providers.mock_llm import MockLLMProvider

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provider(fixture_dir: Path = _FIXTURE_DIR) -> MockLLMProvider:
    return MockLLMProvider(fixture_dir=fixture_dir)


def _dim_request(dimension: DimensionName) -> ReasoningRequest:
    return ReasoningRequest(
        dimension=dimension,
        summary=f"Test request for {dimension.value}",
        facts=["fact 1", "fact 2"],
    )


def _verdict_request() -> ReasoningRequest:
    return ReasoningRequest(
        summary="Verdict synthesis request",
        facts=["scope: 0.96", "estimation: 0.99"],
    )


# ---------------------------------------------------------------------------
# Provider name
# ---------------------------------------------------------------------------


def test_provider_name():
    assert _provider().name == "MockLLMProvider"


# ---------------------------------------------------------------------------
# DimensionReasoning fixtures
# ---------------------------------------------------------------------------


def test_scope_fixture_returns_dimension_reasoning():
    result = _provider().reason(_dim_request(DimensionName.SCOPE), DimensionReasoning)
    assert isinstance(result, DimensionReasoning)
    assert result.classification == "delivered"
    assert len(result.narrative) > 20


def test_estimation_fixture_returns_dimension_reasoning():
    result = _provider().reason(_dim_request(DimensionName.ESTIMATION), DimensionReasoning)
    assert isinstance(result, DimensionReasoning)
    assert result.classification == "within_tolerance"
    assert result.risk_factors == []


def test_environment_fixture_has_minor_risk():
    result = _provider().reason(_dim_request(DimensionName.ENVIRONMENT), DimensionReasoning)
    assert isinstance(result, DimensionReasoning)
    assert len(result.risk_factors) == 1
    assert result.risk_factors[0].severity == RiskSeverity.MINOR


def test_test_readiness_fixture_returns_dimension_reasoning():
    result = _provider().reason(_dim_request(DimensionName.TEST_READINESS), DimensionReasoning)
    assert isinstance(result, DimensionReasoning)
    assert result.classification == "suite_passing"


def test_dependency_fixture_returns_dimension_reasoning():
    result = _provider().reason(_dim_request(DimensionName.DEPENDENCY), DimensionReasoning)
    assert isinstance(result, DimensionReasoning)
    assert result.risk_factors == []


# ---------------------------------------------------------------------------
# VerdictSynthesis fixture
# ---------------------------------------------------------------------------


def test_verdict_synthesis_fixture():
    result = _provider().reason(_verdict_request(), VerdictSynthesis)
    assert isinstance(result, VerdictSynthesis)
    assert len(result.rationale) > 50
    assert len(result.remediation) >= 1


# ---------------------------------------------------------------------------
# Missing-fixture fallback (uses RuleBasedProvider silently)
# ---------------------------------------------------------------------------


def test_missing_fixture_falls_back_gracefully(tmp_path: Path):
    """An empty fixture dir should NOT raise — falls back to RuleBasedProvider."""
    provider = MockLLMProvider(fixture_dir=tmp_path)
    result = provider.reason(_verdict_request(), VerdictSynthesis)
    assert isinstance(result, VerdictSynthesis)
    assert len(result.rationale) > 0


# ---------------------------------------------------------------------------
# load_fixture_raw helper
# ---------------------------------------------------------------------------


def test_load_fixture_raw_scope():
    raw = _provider().load_fixture_raw("scope")
    assert "classification" in raw
    assert "narrative" in raw


def test_load_fixture_raw_missing_returns_empty_dict(tmp_path: Path):
    raw = MockLLMProvider(fixture_dir=tmp_path).load_fixture_raw("nonexistent")
    assert raw == {}
