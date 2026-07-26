"""``AssessmentOutputModel`` — the versioned, emitted result (FR-18, schema "1.0.0").

The single object the CLI serialises (verdict line, ``--verbose`` JSON) and the
canonical record persisted to SQLite. Composes the per-dimension results, trends
vs the previous assessment (FR-9), the LLM verdict rationale/remediation (FR-22),
the benchmark context (RAG, FR-24), and the audit trail (FR-25, NFR-3).

Note the two score scales: dimension scores are floats 0.0-1.0; the headline
``score`` is the weighted result scaled to an integer 0-100 (matches the CLI
``SCORE: 84`` line, FR-16). Verdict/score consistency (including cap gates) is the
orchestrator's responsibility (ADR-0013), deliberately not re-enforced here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal

from pydantic import Field

from rrr.models.base import RRRModel, utc_now
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, ReleaseRiskTier, TrendDirection, Verdict
from rrr.models.evidence import RiskFactor, ToolInvocationModel

SCHEMA_VERSION: Final = "1.0.0"


class TrendData(RRRModel):
    """Per-dimension trend vs the previous assessment (FR-9)."""

    dimension: DimensionName
    previous_score: float | None = Field(default=None, ge=0.0, le=1.0)
    current_score: float = Field(ge=0.0, le=1.0)
    delta: float = Field(ge=-1.0, le=1.0)
    direction: TrendDirection


class Benchmark(RRRModel):
    """How this release compares to similar prior releases (RAG over Chroma, FR-24).

    Baseline source is an open question (Phase 2/3); kept minimal and optional so
    the output is valid before benchmarking lands."""

    basis: str = Field(
        default="",
        description="What the comparison is drawn from, e.g. 'prior Retirement-Services releases'.",
    )
    average_score: float | None = Field(default=None, ge=0.0, le=100.0)
    sample_size: int = Field(default=0, ge=0)
    note: str = ""


class AuditTrail(RRRModel):
    """The provenance behind the verdict (NFR-3, FR-25): which provider/model ran,
    token usage, the effective weights after redistribution (FR-7), every tool
    call, and which cap gates fired (ADR-0013)."""

    provider: str = Field(min_length=1, description="LLMProvider used, e.g. 'RuleBasedProvider'.")
    model: str | None = None
    token_usage: dict[str, int] | None = None
    effective_weights: dict[DimensionName, float] = Field(default_factory=dict)
    tool_invocations: list[ToolInvocationModel] = Field(default_factory=list)
    gates_triggered: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AssessmentOutputModel(RRRModel):
    """The complete, versioned assessment result."""

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    release: str = Field(min_length=1, description="Brain ir_name under assessment.")
    value_stream: str = ""
    generated_at: datetime = Field(default_factory=utc_now)

    verdict: Verdict
    score: int = Field(ge=0, le=100, description="Weighted score scaled to 0-100 (FR-16).")
    tier: ReleaseRiskTier | None = Field(
        default=None,
        description=(
            "Release risk tier selected for this assessment (ADR-0016 items 4-5). "
            "None means the global thresholds were used (no --tier flag)."
        ),
    )
    ship_safety_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Weighted sub-score across ship-safety dimensions (Test Readiness, "
            "Environment, Dependency) scaled to 0-100 (ADR-0016 item 6)."
        ),
    )
    delivery_performance_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Weighted sub-score across delivery-performance dimensions (Scope, "
            "Estimation) scaled to 0-100 (ADR-0016 item 6)."
        ),
    )
    aggregate_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Mean confidence across available dimensions (ADR-0015).",
    )

    dimensions: list[DimensionResult] = Field(default_factory=list)
    trend_data: list[TrendData] = Field(default_factory=list)
    progress_highlights: list[str] = Field(default_factory=list)
    benchmark: Benchmark | None = None

    rationale: str = Field(default="", description="LLM verdict rationale (FR-22).")
    remediation: list[str] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(
        default_factory=list,
        description="Verdict-level risks, incl. triggered cap gates (ADR-0013).",
    )

    audit_trail: AuditTrail
