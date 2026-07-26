"""Production readiness input contract — ``production_readiness.json`` (ADR-0016 item 14).

RRR-owned contract describing the go-live readiness checklist: capacity, feature
flags, stakeholder sign-offs, communications, and monitoring plan. Gate-only
(weight = 0): contributes only via risk-factor severity.

Scoring lives in ProductionReadinessAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class ProductionReadinessInput(InputContract):
    """Go-live readiness posture for a release (ADR-0016 item 14, gate-only).

    Stakeholder sign-offs are modelled as a dict (role → signed: bool | None) so
    new roles can be added without a schema version bump. The assessor iterates
    the dict and raises MAJOR risks for any unsigned role.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the go-live checklist was captured.",
    )
    capacity_confirmed: bool = Field(
        default=False,
        description=(
            "True if production capacity (compute, memory, DB connections, quotas) "
            "has been verified and is sufficient for the expected post-release load."
        ),
    )
    feature_flags_configured: bool | None = Field(
        default=None,
        description=(
            "True if feature flags controlling new functionality are configured "
            "correctly in the production flag service. "
            "None if no feature flags are used in this release."
        ),
    )
    go_live_checklist_complete: bool = Field(
        default=False,
        description=(
            "True if every item on the team's go-live checklist has been ticked off "
            "and the checklist has been reviewed by the release coordinator."
        ),
    )
    stakeholder_sign_offs: dict[str, bool | None] = Field(
        default_factory=dict,
        description=(
            "Map of stakeholder role to sign-off status: True = signed, "
            "False = declined, None = pending. "
            "Expected roles: product, engineering, security, operations."
        ),
    )
    release_comms_prepared: bool = Field(
        default=False,
        description=(
            "True if release communications (internal announcements, customer notices, "
            "changelog entries) have been drafted, reviewed, and are ready to send."
        ),
    )
    support_team_briefed: bool = Field(
        default=False,
        description=(
            "True if the support and customer-success teams have been briefed on "
            "new features, known issues, and the escalation path for this release."
        ),
    )
    rollback_decision_criteria_defined: bool = Field(
        default=False,
        description=(
            "True if the team has defined explicit criteria that would trigger a "
            "rollback decision post-release (e.g. error rate > X%, SLO breach, "
            "P1 incident within Y minutes of go-live)."
        ),
    )
    post_release_monitoring_plan: bool = Field(
        default=False,
        description=(
            "True if a post-release monitoring plan exists: dashboards to watch, "
            "on-call person assigned, and minimum monitoring duration defined."
        ),
    )
