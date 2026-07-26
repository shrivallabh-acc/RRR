"""Operational input contract — ``operational.json`` (ADR-0016, operational-schema.md).

RRR-owned contract describing deployment pipeline health and rollback readiness.
Kept separate from the brain extract (ADR-0012) because this data comes from the
release manager's deployment tooling, not from RKT Program Metrics.

Scoring lives in the Operational assessor; this model only validates shape and
enum membership.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import PipelineStatus, RollbackStatus


class OperationalInput(InputContract):
    """Deployment readiness snapshot for a release (ADR-0016).

    All fields default to safe-but-uncertain values so an incomplete file still
    loads; the assessor converts ``unknown`` to partial scores with reduced
    confidence rather than failing the dimension entirely.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    deployment_pipeline: PipelineStatus = Field(
        default=PipelineStatus.UNKNOWN,
        description="CI/CD pipeline health: green (all passing) / yellow (flaky) / red (broken).",
    )
    rollback_plan: RollbackStatus = Field(
        default=RollbackStatus.UNKNOWN,
        description="Rollback plan completeness: documented / partial / none.",
    )
    change_freeze: bool = Field(
        default=False,
        description=(
            "True if a change-freeze window is active — blocks release regardless of score."
        ),
    )
    recent_deployment_failures: int = Field(
        default=0,
        ge=0,
        description="Number of failed deployments to production in the last 30 days.",
    )
    deployment_duration_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Typical deployment runtime in minutes — None if not yet deployed.",
    )
