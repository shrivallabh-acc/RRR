"""Input contract for the ObservabilityAssessor — monitoring, alerting, and tracing coverage.

Captures dashboard configuration, SLO definition and alerting coverage, distributed
trace coverage, log coverage, and runbook-to-alert linkage. Added as part of the
OperationalAssessor split (ADR-0016 item 7). Read by ObservabilitySourceReader
from ``data/observability.json`` or a localhost API.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class ObservabilityInput(InputContract):
    """Monitoring, alerting, and trace coverage fields for one release.

    Coverage percentages are in the 0-100 range. All fields default to a
    conservative zero-coverage posture so a partial stub produces a worst-case
    score with reduced confidence (rather than crashing).
    """

    schema_version: str = Field(
        default="1.0.0",
        description="Schema version for forward-compatibility detection.",
    )
    release: str | None = Field(
        default=None,
        description="Release IR name — cross-reference with brain data; not required.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of when this snapshot was captured.",
    )
    dashboards_configured: bool = Field(
        default=False,
        description="True when release-specific dashboards are set up in the monitoring tool.",
    )
    dashboards_count: int = Field(
        default=0,
        ge=0,
        description="Number of dashboards covering this release's services.",
    )
    slo_defined: bool = Field(
        default=False,
        description="True when Service Level Objectives are formally defined for this release.",
    )
    slo_alerts_configured: bool = Field(
        default=False,
        description="True when alert rules fire on SLO budget burn-down.",
    )
    alert_coverage_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of services/endpoints covered by alerts (0-100).",
    )
    trace_coverage_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of critical paths instrumented with distributed tracing (0-100).",
    )
    log_coverage_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of services emitting structured logs (0-100).",
    )
    runbooks_linked_to_alerts_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of alerts that link to a runbook (0-100).",
    )
    monitoring_tool: str | None = Field(
        default=None,
        description="Name of the primary monitoring/alerting tool (e.g. 'grafana', 'datadog').",
    )
