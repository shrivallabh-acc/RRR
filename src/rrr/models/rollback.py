"""Input contract for the RollbackAssessor — rollback plan completeness and test evidence.

Captures whether a rollback plan exists, has been tested, meets RTO/RPO targets,
and whether a data-rollback plan exists when applicable. Added as part of the
OperationalAssessor split (ADR-0016 item 7). Gate-only: no score weight.
Read by RollbackSourceReader from ``data/rollback.json`` or a localhost API.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import RollbackStatus


class RollbackInput(InputContract):
    """Rollback plan existence, test evidence, and data-rollback coverage for one release.

    All fields default to an unknown/false posture so a partial stub still
    validates and surfaces as a conservative gate assessment rather than a crash.
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
    rollback_plan: RollbackStatus = Field(
        default=RollbackStatus.UNKNOWN,
        description="Rollback plan completeness: documented / partial / none / unknown.",
    )
    rollback_tested: bool = Field(
        default=False,
        description=(
            "True when the rollback procedure has been exercised in a non-prod environment."
        ),
    )
    rollback_test_date: str | None = Field(
        default=None,
        description="ISO 8601 date of the most recent rollback test; None if never tested.",
    )
    estimated_rollback_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Estimated time to complete a rollback in minutes; None if unknown.",
    )
    automated_rollback_available: bool = Field(
        default=False,
        description="True when the rollback can be triggered automatically without human steps.",
    )
    data_rollback_applicable: bool = Field(
        default=False,
        description=(
            "True when this release includes data migrations"
            " that require a data rollback plan."
        ),
    )
    data_rollback_plan_exists: bool | None = Field(
        default=None,
        description=(
            "True when a data rollback plan is documented and approved. "
            "Null when data_rollback_applicable is False."
        ),
    )
