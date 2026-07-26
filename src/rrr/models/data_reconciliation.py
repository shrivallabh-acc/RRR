"""Data reconciliation input contract — ``data_reconciliation.json`` (ADR-0016 item 11).

RRR-owned contract describing data migration integrity. This dimension is opt-in
and only meaningful when a data migration is part of the release. Gate-only
(weight = 0): contributes only via risk-factor severity.

Scoring lives in DataReconciliationAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class DataReconciliationInput(InputContract):
    """Data migration reconciliation posture for a release (ADR-0016 item 11, gate-only).

    When ``migration_applicable`` is False the assessor passes all checks without
    raising risk factors — the gate is a no-op for releases without data migration.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when reconciliation was assessed.",
    )
    migration_applicable: bool = Field(
        default=False,
        description=(
            "True if this release includes a data migration. "
            "False means all reconciliation checks are bypassed."
        ),
    )
    pre_migration_record_count: int | None = Field(
        default=None,
        ge=0,
        description="Record count in the source system before migration. None if not captured.",
    )
    post_migration_record_count: int | None = Field(
        default=None,
        ge=0,
        description="Record count in the target system after migration. None if not captured.",
    )
    reconciliation_run: bool = Field(
        default=False,
        description="True if an automated reconciliation check was executed after migration.",
    )
    reconciliation_date: str | None = Field(
        default=None,
        description="ISO 8601 date when reconciliation was last run.",
    )
    discrepancy_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of records that could not be matched between source and target. "
            "Zero is required for a clean gate."
        ),
    )
    discrepancy_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Discrepancy count as a percentage of total migrated records.",
    )
    reconciliation_approved: bool | None = Field(
        default=None,
        description=(
            "True if the data owner / DBA has signed off the reconciliation report. "
            "None means the approval step has not yet been completed."
        ),
    )
