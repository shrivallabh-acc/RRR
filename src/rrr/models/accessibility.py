"""Accessibility input contract — ``accessibility.json`` (ADR-0016 item 8).

RRR-owned contract describing WCAG compliance scan results and manual review
outcomes. Gate-only dimension (weight = 0): contributes only via risk-factor
severity, never by averaging into the weighted score.

Scoring lives in AccessibilityAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class AccessibilityInput(InputContract):
    """WCAG compliance posture snapshot for a release (ADR-0016 item 8, gate-only).

    All fields default to safe-but-uncertain values so an incomplete file still
    loads. The assessor treats missing violations as zero and absent manual review
    as not yet complete, scoring conservatively.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the scan data was collected.",
    )
    wcag_target_level: str = Field(
        default="AA",
        description="Target WCAG conformance level: A, AA, or AAA.",
    )
    scan_tool: str | None = Field(
        default=None,
        description="Name of the automated accessibility scanning tool used (e.g. axe, Wave).",
    )
    pages_scanned: int = Field(
        default=0,
        ge=0,
        description="Number of pages or views included in the automated scan.",
    )
    critical_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of WCAG critical violations — barriers that prevent access "
            "for users with disabilities (e.g. missing alt text on images, absent labels)."
        ),
    )
    major_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of WCAG major violations — significant usability barriers that "
            "severely impact but do not fully block access."
        ),
    )
    minor_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of WCAG minor / advisory violations — best-practice deviations "
            "with low impact on users with disabilities."
        ),
    )
    manual_review_complete: bool = Field(
        default=False,
        description="True if a human accessibility expert review has been completed.",
    )
    manual_review_passed: bool | None = Field(
        default=None,
        description=(
            "True if the manual review concluded the release meets the target WCAG level. "
            "None if the review has not yet been completed."
        ),
    )
