"""Input contract for the OperabilityAssessor — deployment pipeline and day-2 ops readiness.

Captures the deployment pipeline health, runbook completeness, on-call coverage,
and change-management approval state for a release. Supersedes the pipeline and
change-freeze fields from the old OperationalInput (ADR-0016 item 7 split).
Read by OperabilitySourceReader from ``data/operability.json`` or a localhost API.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import PipelineStatus


class OperabilityInput(InputContract):
    """Deployment pipeline health and operational-readiness fields for one release.

    All fields default to a conservative unknown/false posture so a partial stub
    still validates and produces a worst-case assessment (reduced confidence).
    """

    schema_version: str = Field(
        default="1.0.0",
        description="Schema version for forward-compatibility detection.",
    )
    release: str | None = Field(
        default=None,
        description="Release IR name — used for cross-reference with brain data; not required.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of when this snapshot was captured.",
    )
    deployment_pipeline: PipelineStatus = Field(
        default=PipelineStatus.UNKNOWN,
        description="CI/CD pipeline status at snapshot time: green / yellow / red / unknown.",
    )
    change_freeze: bool = Field(
        default=False,
        description=(
            "True if a change-freeze window is active"
            " — hard blocker regardless of pipeline."
        ),
    )
    recent_deployment_failures: int = Field(
        default=0,
        ge=0,
        description="Number of failed deployments in the last 30 days (advisory signal).",
    )
    deployment_duration_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Typical deployment duration in minutes; None if not measured.",
    )
    runbook_complete: bool = Field(
        default=False,
        description="True when the operational runbook exists and is current.",
    )
    runbook_last_tested_days_ago: int | None = Field(
        default=None,
        ge=0,
        description="Days since the runbook was last tested end-to-end; None if never tested.",
    )
    on_call_schedule_active: bool = Field(
        default=False,
        description="True when an on-call schedule is active and covers the release window.",
    )
    escalation_paths_defined: bool = Field(
        default=False,
        description="True when escalation paths for critical incidents are documented.",
    )
    change_mgmt_approved: bool = Field(
        default=False,
        description="True when the change-management board has approved this release.",
    )
    operational_docs_reviewed: bool = Field(
        default=False,
        description="True when operational documentation has been reviewed for this release.",
    )
