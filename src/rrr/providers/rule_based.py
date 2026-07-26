"""``RuleBasedProvider`` — the deterministic, offline default (ADR-0006).

No model, no network: it composes templated narratives and echoes the
deterministically-detected risk factors carried in the :class:`ReasoningRequest`.
It is also the guardrail fallback when a model provider's output cannot be
validated (ADR-0009). Output is fully reproducible — identical request, identical
result — which keeps it usable in CI and as the determinism baseline.

It builds the known reasoning models directly (so it can never fail validation).
New reasoning models register a builder via :meth:`register`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from pydantic import BaseModel

from rrr.errors import ProviderError
from rrr.models.llm import DimensionReasoning, VerdictSynthesis
from rrr.providers.base import LLMProvider, ReasoningModel, ReasoningRequest

_NO_OBSERVATIONS = "No additional observations."
_Builder = Callable[[ReasoningRequest], BaseModel]


class RuleBasedProvider(LLMProvider):
    """Deterministic prose/risk composer over precomputed facts."""

    def __init__(self) -> None:
        self._builders: dict[type[BaseModel], _Builder] = {
            DimensionReasoning: self._build_dimension_reasoning,
            VerdictSynthesis: self._build_verdict_synthesis,
        }

    @property
    def name(self) -> str:
        return "RuleBasedProvider"

    def register(self, response_model: type[BaseModel], builder: _Builder) -> None:
        """Register a deterministic builder for an additional reasoning model."""
        self._builders[response_model] = builder

    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[ReasoningModel],
    ) -> ReasoningModel:
        """Satisfy a reasoning request by dispatching to the registered deterministic builder.

        Each response model type has a builder registered at startup via register().
        The builder reads from request.facts and request.summary and constructs the
        response without any model call — this is the always-available fallback that
        keeps the pipeline working when no LLM is configured (ADR-0005, ADR-0006).
        """
        builder = self._builders.get(response_model)
        if builder is None:
            raise ProviderError(f"{self.name} has no builder for {response_model.__name__}")
        return cast(ReasoningModel, builder(request))

    @staticmethod
    def _compose(summary: str, facts: list[str], *, fallback: str) -> str:
        """Join summary + facts into one prose string, skipping blank entries.

        The summary is the first sentence; each fact becomes a following sentence.
        If nothing is available (empty summary and no facts) the fallback phrase is
        returned so the narrative field is never left empty.
        """
        parts = [p for p in (summary, *facts) if p]
        return " ".join(parts) if parts else fallback

    def _build_dimension_reasoning(self, request: ReasoningRequest) -> DimensionReasoning:
        """Produce a DimensionReasoning result without calling any model.

        The classification comes straight from the deterministic assessment (the
        assessor already computed it). The narrative is assembled from the summary
        and facts that the assessor gathered. Risk factors are passed through
        unchanged — the rule-based provider does not add or remove any.
        """
        return DimensionReasoning(
            classification=request.classification or "unclassified",
            narrative=self._compose(request.summary, request.facts, fallback=_NO_OBSERVATIONS),
            risk_factors=list(request.risk_factors),
        )

    def _build_verdict_synthesis(self, request: ReasoningRequest) -> VerdictSynthesis:
        """Produce a VerdictSynthesis result without calling any model.

        The rationale is the cross-dimension summary from the orchestrator's request.
        Remediation items are generated from the collected risk factors — each item
        names the severity and describes the problem so the release manager knows
        what to fix and how urgent it is.
        """
        remediation = [
            f"Address ({rf.severity.value}): {rf.description}" for rf in request.risk_factors
        ]
        rationale = self._compose(
            request.summary, request.facts, fallback="No cross-dimension findings."
        )
        return VerdictSynthesis(rationale=rationale, remediation=remediation)
