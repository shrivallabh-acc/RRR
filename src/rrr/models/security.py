"""Security & compliance input contract — ``security.json`` (ADR-0016, FR-security).

RRR-owned contract describing static-analysis scan results, open CVE counts, and
governance approvals. Kept separate from the brain extract (ADR-0012) because this
data comes from the security toolchain (SAST/DAST scanners, CVE registries) rather
than from RKT Program Metrics.

Scoring lives in the SecurityComplianceAssessor; this model only validates shape
and enum membership. The dimension is gate-only (weight = 0): it contributes only
via risk-factor severity, never by averaging into the weighted score.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import DastStatus, SastStatus


class SecurityInput(InputContract):
    """Security posture snapshot for a release (ADR-0016, gate-only dimension).

    All fields default to safe-but-uncertain values so an incomplete file still
    loads. The assessor treats missing fields as NOT_RUN / None — it scores
    conservatively and reduces confidence rather than failing the dimension.
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
    sast_status: SastStatus = Field(
        default=SastStatus.NOT_RUN,
        description="Static Application Security Testing result: passed / failed / not_run.",
    )
    dast_status: DastStatus = Field(
        default=DastStatus.NOT_RUN,
        description="Dynamic Application Security Testing result: passed / failed / not_run.",
    )
    open_critical_cves: int = Field(
        default=0,
        ge=0,
        description="Count of open critical-severity CVEs in the release image / dependencies.",
    )
    open_high_cves: int = Field(
        default=0,
        ge=0,
        description="Count of open high-severity CVEs (below critical).",
    )
    license_approved: bool | None = Field(
        default=None,
        description=(
            "True if all dependency licences have been reviewed and approved. "
            "None means the review has not been completed."
        ),
    )
    data_privacy_approved: bool | None = Field(
        default=None,
        description=(
            "True if data-privacy / GDPR impact assessment has been signed off. "
            "None means the review is pending."
        ),
    )
    pen_test_passed: bool | None = Field(
        default=None,
        description=(
            "True if a penetration test was conducted and passed. "
            "False if pen-test found issues; None if not yet run."
        ),
    )
