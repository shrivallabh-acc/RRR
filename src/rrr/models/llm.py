"""LLM provider I/O — the schema-validated structured outputs (FR-21/22/23).

``LLMProvider.reason(prompt, schema)`` must return one of these, validated by
Pydantic. On validation failure or refusal the provider does one repair retry,
then falls back to ``RuleBasedProvider`` with reduced confidence (ADR-0009).
The numeric score is never taken from these models — the LLM contributes
classification, narrative, risk factors and remediation only (ADR-0006).

Models are strict (``extra="forbid"`` via :class:`RRRModel`) so a hallucinated
field fails validation and triggers the repair/fallback path rather than passing
silently.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import RRRModel
from rrr.models.evidence import RiskFactor


class DimensionReasoning(RRRModel):
    """Per-assessor reasoning output (FR-21): classify ambiguous items, extract
    risk factors, write the narrative. The score stays deterministic in the
    assessor; this only adds judgement and prose."""

    classification: str = Field(
        min_length=1,
        description="Dimension-specific label chosen by the model.",
    )
    narrative: str = Field(
        min_length=1,
        description="Human-readable evidence narrative for this dimension.",
    )
    risk_factors: list[RiskFactor] = Field(default_factory=list)


class VerdictSynthesis(RRRModel):
    """Orchestrator-level synthesis (FR-22): the cross-dimension verdict rationale
    and remediation plan. The verdict *label* itself is derived from the
    deterministic score, not from this text."""

    rationale: str = Field(
        min_length=1,
        description="Why the release earned its verdict, across dimensions.",
    )
    remediation: list[str] = Field(
        default_factory=list,
        description="Ordered, actionable remediation steps.",
    )
