"""Auditability input contract — ``auditability.json`` (ADR-0016 item 9).

RRR-owned contract describing audit-trail completeness and compliance posture.
Gate-only dimension (weight = 0): contributes only via risk-factor severity,
never by averaging into the weighted score.

Scoring lives in AuditabilityAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class AuditabilityInput(InputContract):
    """Audit-trail posture snapshot for a release (ADR-0016 item 9, gate-only).

    All fields default to the most conservative value (logging disabled, reviews
    incomplete) so an incomplete file is assessed pessimistically rather than
    optimistically, preserving the gate's protective intent.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the audit posture was assessed.",
    )
    audit_logging_enabled: bool = Field(
        default=False,
        description=(
            "True if structured audit logging is active for all regulated transactions. "
            "False means critical events may be unrecorded."
        ),
    )
    regulated_events_logged: bool = Field(
        default=False,
        description=(
            "True if every event category mandated by the applicable regulation "
            "(e.g. SOX, FCA, GDPR) is captured in the audit log."
        ),
    )
    audit_log_immutability_guaranteed: bool = Field(
        default=False,
        description=(
            "True if the audit log is write-once / append-only and cannot be "
            "modified or deleted without detection (e.g. WORM storage, blockchain anchor)."
        ),
    )
    data_retention_days: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Configured audit log retention in days. "
            "None means the retention policy has not been set."
        ),
    )
    gdpr_logging_compliant: bool | None = Field(
        default=None,
        description=(
            "True if the audit log design complies with GDPR data-minimisation and "
            "right-to-erasure requirements. None if the review has not been completed."
        ),
    )
    pii_access_logged: bool = Field(
        default=False,
        description=(
            "True if every access to personally identifiable information is captured "
            "in the audit log with user identity, timestamp, and data classification."
        ),
    )
    audit_trail_tested: bool = Field(
        default=False,
        description=(
            "True if the audit trail has been validated end-to-end — data written, "
            "queried, and confirmed complete by an independent test run."
        ),
    )
