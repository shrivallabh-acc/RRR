"""Performance / NFR input contract — ``performance.json`` (ADR-0016).

RRR-owned contract describing load-test outcomes, P99 latency vs SLO, and
capacity headroom. Kept separate from the brain extract (ADR-0012) because this
data originates from the performance toolchain (load runners, APM, capacity
planners) rather than from RKT Program Metrics.

Scoring lives in the PerformanceAssessor; this model only validates shape and
enum membership. The dimension is gate-only (weight = 0): it contributes only
via risk-factor severity, never by averaging into the weighted score.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import PerformanceTestStatus


class PerformanceInput(InputContract):
    """Performance and NFR posture snapshot for a release (ADR-0016, gate-only dimension).

    All fields default to safe-but-uncertain values so an incomplete file still
    loads. The assessor treats missing numeric fields as unknown and reduces
    confidence rather than failing the dimension outright.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the performance data was collected.",
    )
    performance_test_status: PerformanceTestStatus = Field(
        default=PerformanceTestStatus.NOT_RUN,
        description="Overall load / performance test result: passed / failed / not_run.",
    )
    p99_latency_ms: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Observed P99 response time in milliseconds from the most recent load test. "
            "None means no measurement is available."
        ),
    )
    slo_p99_threshold_ms: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "SLO target for P99 latency in milliseconds. "
            "When set, the assessor compares p99_latency_ms against this threshold. "
            "None means no SLO has been defined for this release."
        ),
    )
    capacity_headroom_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Available capacity headroom as a percentage of peak observed load. "
            "For example, 40.0 means the system can absorb 40% more traffic. "
            "None means capacity data is not available."
        ),
    )
