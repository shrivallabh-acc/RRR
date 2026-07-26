"""Tests for the provider layer: RuleBasedProvider + the repair-loop guardrail."""

from __future__ import annotations

import pytest

from rrr.errors import ProviderError, ProviderValidationError
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.llm import DimensionReasoning, VerdictSynthesis
from rrr.providers import (
    LLMProvider,
    ReasoningRequest,
    RuleBasedProvider,
    parse_with_repair,
)

RISK = RiskFactor(description="Primary DB not validated", severity=RiskSeverity.MINOR)


def test_rule_based_is_an_llm_provider() -> None:
    assert isinstance(RuleBasedProvider(), LLMProvider)
    assert RuleBasedProvider().name == "RuleBasedProvider"


def test_dimension_reasoning_built_from_facts() -> None:
    req = ReasoningRequest(
        dimension=DimensionName.SCOPE,
        summary="230 of 240 SP closed (95.8%).",
        classification="delivered",
        facts=["Velocity rising over last 3 weeks."],
        risk_factors=[RISK],
    )
    out = RuleBasedProvider().reason(req, DimensionReasoning)
    assert isinstance(out, DimensionReasoning)
    assert out.classification == "delivered"
    assert "230 of 240" in out.narrative and "Velocity" in out.narrative
    assert out.risk_factors == [RISK]


def test_dimension_reasoning_narrative_has_fallback_when_empty() -> None:
    out = RuleBasedProvider().reason(ReasoningRequest(), DimensionReasoning)
    assert out.narrative  # min_length=1 satisfied
    assert out.classification == "unclassified"


def test_verdict_synthesis_derives_remediation_from_risks() -> None:
    req = ReasoningRequest(summary="4 of 5 dimensions strong.", risk_factors=[RISK])
    out = RuleBasedProvider().reason(req, VerdictSynthesis)
    assert isinstance(out, VerdictSynthesis)
    assert out.rationale
    assert out.remediation == ["Address (minor): Primary DB not validated"]


def test_unknown_response_model_raises() -> None:
    from rrr.models.dimension import DimensionResult

    with pytest.raises(ProviderError, match="no builder"):
        RuleBasedProvider().reason(ReasoningRequest(), DimensionResult)


def test_rule_based_is_deterministic() -> None:
    req = ReasoningRequest(summary="x", facts=["a", "b"], risk_factors=[RISK])
    provider = RuleBasedProvider()
    assert provider.reason(req, DimensionReasoning) == provider.reason(req, DimensionReasoning)


def test_register_extends_builders() -> None:
    provider = RuleBasedProvider()
    provider.register(
        DimensionReasoning,
        lambda _req: DimensionReasoning(classification="custom", narrative="custom"),
    )
    assert provider.reason(ReasoningRequest(), DimensionReasoning).classification == "custom"


# --- guardrail repair loop (ADR-0009) ---------------------------------------------------------

_VALID = DimensionReasoning(classification="delivered", narrative="ok").model_dump_json()


def test_repair_loop_returns_on_first_valid_output() -> None:
    calls: list[str | None] = []

    def generate(hint: str | None) -> str:
        calls.append(hint)
        return _VALID

    out = parse_with_repair(generate, DimensionReasoning)
    assert out.classification == "delivered"
    assert calls == [None]  # no repair needed


def test_repair_loop_retries_with_error_hint_then_succeeds() -> None:
    calls: list[str | None] = []

    def generate(hint: str | None) -> str:
        calls.append(hint)
        return "{}" if hint is None else _VALID  # first call invalid, repair succeeds

    out = parse_with_repair(generate, DimensionReasoning)
    assert out.classification == "delivered"
    assert len(calls) == 2 and calls[0] is None and calls[1] is not None  # hint fed back


def test_repair_loop_raises_after_exhausting_attempts() -> None:
    def generate(hint: str | None) -> str:
        return "{}"  # always invalid

    with pytest.raises(ProviderValidationError, match="DimensionReasoning"):
        parse_with_repair(generate, DimensionReasoning)
