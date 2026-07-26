"""Tests for the BaseAssessor template (FR-12, FR-13, ADR-0005, ADR-0009)."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from rrr.assessors import BaseAssessor, DeterministicAssessment
from rrr.errors import ProviderValidationError, ToolError, ToolTimeoutError
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.llm import DimensionReasoning
from rrr.providers import LLMProvider, ReasoningRequest, RuleBasedProvider
from rrr.tools.runner import ToolRunner

RISK = RiskFactor(description="Primary DB not validated", severity=RiskSeverity.MINOR)


class _Echo:
    name = "echo"

    def invoke(self, **params: Any) -> Any:
        return params.get("value", "ok")


class _Boom:
    name = "boom"

    def invoke(self, **params: Any) -> Any:
        raise ValueError("kaboom")


class _Failing(LLMProvider):
    @property
    def name(self) -> str:
        return "failing"

    def reason(self, request: ReasoningRequest, response_model: type[Any]) -> Any:
        raise ProviderValidationError("cannot validate")


DetFn = Callable[[BaseAssessor], DeterministicAssessment]


class _Dim(BaseAssessor):
    """Test assessor that delegates the deterministic core to an injected function."""

    def __init__(self, runner: ToolRunner, provider: LLMProvider, det_fn: DetFn) -> None:
        super().__init__(runner, provider)
        self._det_fn = det_fn

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.SCOPE

    def _assess(self) -> DeterministicAssessment:
        return self._det_fn(self)


def _make(det_fn: DetFn, provider: LLMProvider | None = None) -> _Dim:
    return _Dim(ToolRunner(), provider or RuleBasedProvider(), det_fn)


def test_happy_path_assembles_dimension_result() -> None:
    def det(a: BaseAssessor) -> DeterministicAssessment:
        a.invoke_tool(_Echo(), value="data")
        return DeterministicAssessment(
            score=0.95,
            classification="delivered",
            summary="230 of 240 SP closed.",
            facts=["Velocity rising."],
            risk_factors=[RISK],
            evidence=[a.build_evidence("completion", 0.95, "230/240", tool="echo")],
        )

    result = _make(det).assess()
    assert result.dimension is DimensionName.SCOPE and result.available is True
    assert result.score == 0.95 and result.confidence == 1.0
    assert result.classification == "delivered"
    assert "230 of 240" in result.narrative
    assert result.risk_factors == [RISK]
    assert len(result.evidence) == 1 and len(result.tool_invocations) == 1


def test_tool_failure_propagating_marks_dimension_unavailable() -> None:
    def det(a: BaseAssessor) -> DeterministicAssessment:
        a.invoke_tool(_Boom())  # raises ToolError, not caught
        raise AssertionError("unreachable")

    result = _make(det).assess()
    assert result.available is False and result.score == 0.0 and result.confidence == 0.0
    assert len(result.tool_invocations) == 1 and result.tool_invocations[0].success is False


def test_partial_tool_failure_caps_confidence_at_half() -> None:
    def det(a: BaseAssessor) -> DeterministicAssessment:
        a.invoke_tool(_Echo(), value="ok")
        with contextlib.suppress(ToolError):  # assessor chooses to degrade, not crash
            a.invoke_tool(_Boom())
        return DeterministicAssessment(score=0.7, classification="partial", summary="mixed")

    result = _make(det).assess()
    assert result.available is True and result.confidence == 0.5


def test_all_tools_failing_yields_zero_confidence() -> None:
    def det(a: BaseAssessor) -> DeterministicAssessment:
        for _ in range(2):
            with contextlib.suppress(ToolError):
                a.invoke_tool(_Boom())
        return DeterministicAssessment(score=0.0, classification="none", summary="all failed")

    assert _make(det).assess().confidence == 0.0


def test_provider_failure_falls_back_and_reduces_confidence() -> None:
    def det(a: BaseAssessor) -> DeterministicAssessment:
        a.invoke_tool(_Echo(), value="ok")  # tool passes -> would be 1.0
        return DeterministicAssessment(score=0.9, classification="delivered", summary="strong")

    result = _make(det, provider=_Failing()).assess()
    assert result.confidence == 0.5  # capped because reasoning degraded to rule-based
    assert result.classification == "delivered"  # rule-based fallback echoes deterministic class
    assert result.narrative  # composed by fallback


def test_reset_allows_instance_reuse_without_state_bleed() -> None:
    def det(a: BaseAssessor) -> DeterministicAssessment:
        a.invoke_tool(_Echo(), value="x")
        return DeterministicAssessment(score=0.5, classification="c", summary="s")

    assessor = _make(det)
    first = assessor.assess()
    second = assessor.assess()
    assert len(first.tool_invocations) == 1 and len(second.tool_invocations) == 1


def test_build_evidence_factory() -> None:
    ev = _make(lambda _a: DeterministicAssessment(0.0, "c", "s")).build_evidence(
        "label", 0.5, "detail", tool="echo"
    )
    assert ev.label == "label" and ev.value == 0.5 and ev.tool == "echo"


def test_assessor_with_no_tools_keeps_full_confidence() -> None:
    result = _make(
        lambda _a: DeterministicAssessment(score=1.0, classification="c", summary="s")
    ).assess()
    assert result.confidence == 1.0 and isinstance(result.narrative, str)


def test_reason_uses_dimension_reasoning_shape() -> None:
    # Sanity: the provider path returns the structured model the base expects.
    out = RuleBasedProvider().reason(ReasoningRequest(summary="s"), DimensionReasoning)
    assert isinstance(out, DimensionReasoning)


# ---------------------------------------------------------------------------
# W6 retry tests (NFR-1, ToolsConfig)
# ---------------------------------------------------------------------------


def test_retry_succeeds_on_second_attempt() -> None:
    """A tool that fails once then succeeds should record both invocations and mark available."""
    call_count = 0

    class _Flaky:
        name = "flaky"

        def invoke(self, **params: Any) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("transient glitch")
            return "recovered"

    def det(a: BaseAssessor) -> DeterministicAssessment:
        val = a.invoke_tool(_Flaky())
        return DeterministicAssessment(score=0.8, classification="c", summary=str(val))

    runner = ToolRunner(retry_count=1, retry_backoff_s=0.0)
    result = _Dim(runner, RuleBasedProvider(), det).assess()
    assert result.available is True
    assert call_count == 2
    # Two invocations: one failed attempt + one successful retry
    assert len(result.tool_invocations) == 2
    assert result.tool_invocations[0].success is False
    assert result.tool_invocations[1].success is True


def test_retry_exhausted_marks_dimension_unavailable() -> None:
    """When all retry attempts fail the dimension is unavailable with all invocations recorded."""

    def det(a: BaseAssessor) -> DeterministicAssessment:
        a.invoke_tool(_Boom())
        raise AssertionError("unreachable")

    runner = ToolRunner(retry_count=2, retry_backoff_s=0.0)
    result = _Dim(runner, RuleBasedProvider(), det).assess()
    assert result.available is False
    # 3 invocations total: original attempt + 2 retries, all failed
    assert len(result.tool_invocations) == 3
    assert all(not inv.success for inv in result.tool_invocations)


def test_timeout_error_is_not_retried() -> None:
    """ToolTimeoutError propagates on the first attempt; retry_count is ignored."""
    run_count = 0

    class _AlwaysTimesOut(ToolRunner):
        def run(self, tool: Any, *, timeout: float | None = None, **params: Any) -> Any:
            nonlocal run_count
            run_count += 1
            raise ToolTimeoutError("simulated timeout")

    def det(a: BaseAssessor) -> DeterministicAssessment:
        with contextlib.suppress(ToolError):
            a.invoke_tool(_Echo())
        return DeterministicAssessment(score=0.5, classification="c", summary="partial")

    runner = _AlwaysTimesOut(retry_count=3, retry_backoff_s=0.0)
    _Dim(runner, RuleBasedProvider(), det).assess()
    # Only 1 run despite retry_count=3 — timeout is never retried
    assert run_count == 1
