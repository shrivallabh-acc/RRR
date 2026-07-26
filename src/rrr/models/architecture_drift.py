"""Architecture drift input contract — ``architecture_drift.json`` (ADR-0016 item 16).

RRR-owned contract describing how far the running system has drifted from the
approved architecture baseline (ADRs, tech standards, approved technology list).
Gate-only dimension (weight = 0): contributes only via risk-factor severity.

Scoring lives in ArchitectureDriftAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class ArchitectureDriftInput(InputContract):
    """Architecture baseline compliance posture for a release (ADR-0016 item 16, gate-only).

    ``drift_score`` is a 0–1 float where 0 means no drift and 1 means the system
    has completely diverged from the baseline. The assessor raises MAJOR risk when
    drift exceeds the configured threshold.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the drift assessment was run.",
    )
    baseline_version: str | None = Field(
        default=None,
        description=(
            "Version tag of the architecture baseline this assessment compares against "
            "(e.g. ADR collection commit hash, baseline document version)."
        ),
    )
    tool: str | None = Field(
        default=None,
        description="Tool used to detect drift (e.g. Backstage, custom YAML diff, Steampipe).",
    )
    assessment_date: str | None = Field(
        default=None,
        description="ISO 8601 date when the drift assessment was completed.",
    )
    adr_compliance_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of applicable ADRs whose decisions are reflected in the "
            "current codebase. Below 80% triggers a CRITICAL risk factor."
        ),
    )
    banned_technologies_detected: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of technologies on the approved-technology-list (ATL) banned list "
            "that were detected in the codebase. Any non-zero count is CRITICAL."
        ),
    )
    unapproved_patterns: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of architectural patterns detected that have not been approved "
            "via an ADR or tech-standard document. Triggers MAJOR risk."
        ),
    )
    tech_standard_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of violations of the organisation's technology standards "
            "(e.g. using a deprecated runtime version, non-standard logging framework)."
        ),
    )
    drift_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Overall drift score in [0, 1] produced by the assessment tool. "
            "0 = no drift from baseline; 1 = complete divergence. "
            "Above the configured threshold triggers a MAJOR risk factor."
        ),
    )
    approved_deviations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of known deviations from the baseline that have been formally "
            "approved via an ADR or exception process. These are subtracted from "
            "the raw violation count before risk factors are raised."
        ),
    )
    drift_threshold: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description=(
            "Maximum acceptable drift score before a MAJOR risk factor is raised. "
            "Default 0.20 — more than 20% drift from baseline is high-risk."
        ),
    )
    adr_compliance_threshold_pct: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description=(
            "Minimum ADR compliance percentage before a CRITICAL risk factor is raised. "
            "Default 80% per ADR-0016 item 16."
        ),
    )
