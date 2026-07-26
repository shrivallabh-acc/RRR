"""Audit-trail value objects: tool invocations, evidence, risk factors.

These are RRR-owned, frozen value objects (:class:`RRRModel`). Together they
form the navigable chain of evidence behind every conclusion (NFR-3): a
``DimensionResult`` cites :class:`EvidenceRecord`\\ s, each of which names the
tool that produced it, and every tool call is recorded as a
:class:`ToolInvocationModel` in the audit trail.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from rrr.models.base import RRRModel, utc_now
from rrr.models.enums import DimensionName, RiskSeverity

# Atomic, JSON-serialisable value an evidence record can carry.
EvidenceValue = str | int | float | bool | None


class ToolInvocationModel(RRRModel):
    """A single recorded tool call (FR-11). ``ToolRunner`` produces one per call,
    enforcing the timeout and truncating ``output_summary`` to <=500 chars."""

    name: str = Field(min_length=1)
    params: dict[str, EvidenceValue] = Field(default_factory=dict)
    output_summary: str = Field(default="", max_length=500)
    success: bool
    duration_ms: int = Field(ge=0)
    error_reason: str | None = None
    invoked_at: datetime = Field(default_factory=utc_now)


class EvidenceRecord(RRRModel):
    """One discrete observation supporting a dimension's score/classification.

    ``value`` is the metric used (e.g. completion ratio); ``detail`` is the human
    narrative; ``tool`` links back to the :class:`ToolInvocationModel` that
    produced the underlying data, closing the audit chain."""

    label: str = Field(
        min_length=1,
        description="What is being evidenced, e.g. 'scope_completion'.",
    )
    value: EvidenceValue = None
    detail: str = ""
    tool: str | None = Field(
        default=None,
        description="Name of the tool invocation that sourced this evidence.",
    )


class RiskFactor(RRRModel):
    """A risk surfaced by an assessor. The ``gate`` name links this risk to a named
    entry in ``GatesConfig``; ``GateEngine`` maps it to a verdict cap (ADR-0014).
    Risk factors without a gate name fall back to severity-based capping."""

    description: str = Field(min_length=1)
    severity: RiskSeverity
    dimension: DimensionName | None = None
    gate: str | None = Field(
        default=None,
        description=(
            "Named gate signal (e.g. 'environment_down'). "
            "GateEngine maps this to a verdict cap (ADR-0014)."
        ),
    )
