"""``LLMProvider`` interface and the reasoning-request envelope (FR-21, ADR-0006).

A provider supplies *judgment and prose* — classification, risk factors, narrative,
remediation — never the numeric score or verdict label (ADR-0009 #3). All three
implementations (rule-based default, local LLM, Claude) return the same
schema-validated Pydantic models, so assessor/orchestrator code is provider-agnostic.

:class:`ReasoningRequest` deliberately separates the *instruction* from the *data*:
ingested metrics live in ``facts`` / ``risk_factors`` and are treated as data, never
as instructions (injection safety, ADR-0009 #4). ``allowed_classifications`` bounds
the label space a model may choose from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, Field

from rrr.models.base import RRRModel
from rrr.models.enums import DimensionName
from rrr.models.evidence import RiskFactor

# The structured-output model a reason() call must return (e.g. DimensionReasoning).
ReasoningModel = TypeVar("ReasoningModel", bound=BaseModel)


class ReasoningRequest(RRRModel):
    """Provider-agnostic envelope of deterministic facts to reason over."""

    dimension: DimensionName | None = None
    summary: str = Field(
        default="",
        description="One-line deterministic summary of what was measured.",
    )
    classification: str | None = Field(
        default=None,
        description="Deterministic classification, if the assessor already computed one.",
    )
    facts: list[str] = Field(
        default_factory=list,
        description="Observations to compose the narrative from.",
    )
    risk_factors: list[RiskFactor] = Field(
        default_factory=list,
        description="Deterministically-detected risks to surface/echo.",
    )
    allowed_classifications: list[str] = Field(
        default_factory=list,
        description="Closed set a model may classify into (injection-safe label space).",
    )


class LLMProvider(ABC):
    """Swappable reasoning engine. Implementations select via ``default_config.yaml``."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider id, recorded in the audit trail (FR-25)."""

    @abstractmethod
    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[ReasoningModel],
    ) -> ReasoningModel:
        """Return a schema-validated instance of ``response_model`` (ADR-0009)."""
