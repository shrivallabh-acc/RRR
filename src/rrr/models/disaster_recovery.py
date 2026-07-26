"""Disaster recovery input contract — ``disaster_recovery.json`` (ADR-0016 item 10).

RRR-owned contract describing DR plan completeness and test evidence.
Gate-only dimension (weight = 0): contributes only via risk-factor severity,
never by averaging into the weighted score.

Scoring lives in DisasterRecoveryAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class DisasterRecoveryInput(InputContract):
    """Disaster recovery posture snapshot for a release (ADR-0016 item 10, gate-only).

    All time-based fields accept ISO 8601 strings. Target and tested RTO/RPO are
    in minutes so the assessor can compare them directly without unit conversion.
    None on any tested metric means the DR test has not been run.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the DR posture was assessed.",
    )
    dr_plan_exists: bool = Field(
        default=False,
        description="True if a documented DR plan exists and is approved.",
    )
    dr_last_tested_date: str | None = Field(
        default=None,
        description=(
            "ISO 8601 date of the most recent DR test. "
            "None means the plan has never been tested."
        ),
    )
    rto_target_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Agreed Recovery Time Objective in minutes. None if not defined.",
    )
    rto_tested_minutes: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Actual recovery time achieved in the last DR test, in minutes. "
            "None if the test has not been run."
        ),
    )
    rpo_target_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Agreed Recovery Point Objective in minutes. None if not defined.",
    )
    rpo_tested_minutes: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Actual data loss window measured in the last DR test, in minutes. "
            "None if the test has not been run."
        ),
    )
    failover_tested: bool = Field(
        default=False,
        description=(
            "True if the full failover sequence (primary → DR site) was exercised "
            "successfully in the most recent DR test."
        ),
    )
    data_backup_verified: bool = Field(
        default=False,
        description=(
            "True if backup integrity and restorability were verified in the last "
            "backup validation cycle (restore drill, checksum verification, etc.)."
        ),
    )
    dr_test_max_age_days: int = Field(
        default=180,
        ge=1,
        description=(
            "Maximum acceptable age of the DR test in days. "
            "A test older than this triggers a MAJOR risk factor. Default 180 days (6 months)."
        ),
    )
