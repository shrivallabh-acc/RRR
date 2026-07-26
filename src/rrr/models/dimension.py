"""``DimensionResult`` — the typed output every assessor produces (FR-13).

Carries the deterministic ``score`` and ``confidence`` (both 0.0-1.0), the
LLM-written ``narrative`` and risk factors, the evidence chain, and the recorded
tool invocations. ``available`` flags whether the dimension was successfully
assessed so the orchestrator can redistribute weight on degradation (FR-7,
ADR-0005). The *static* dimension weight is config/orchestrator state, not part
of this result.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import RRRModel
from rrr.models.enums import DimensionName
from rrr.models.evidence import EvidenceRecord, RiskFactor, ToolInvocationModel


class DimensionResult(RRRModel):
    """One dimension's assessment outcome."""

    dimension: DimensionName
    available: bool = Field(
        default=True,
        description="False when the dimension could not be assessed (degrades).",
    )
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    classification: str | None = Field(
        default=None,
        description="Dimension-specific label (e.g. ScopeClass / EstimationClass value).",
    )
    narrative: str = Field(default="", description="LLM-written evidence narrative (FR-21).")
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    tool_invocations: list[ToolInvocationModel] = Field(default_factory=list)
