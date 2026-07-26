"""``PerformanceAssessor`` — load-test outcomes, P99 latency vs SLO, capacity headroom (ADR-0016).

Gate-only dimension: weight = 0 in the weighted score so it cannot be averaged away,
but its risk factors drive verdict caps through the GateEngine (ADR-0013).

Score = 0.5 × perf_status_score + 0.3 × latency_score + 0.2 × capacity_score
The score is informational; the CRITICAL and MAJOR risk factors are the blocking signal.

  perf_status: passed=1.0 / not_run=0.5 / failed=0.0
  latency_score: within SLO → 1.0; at 2× SLO or worse → 0.0; linear in between;
                 no data → 0.5 (uncertain)
  capacity_score: ≥ 40 % headroom → 1.0; 0 % → 0.0; linear in between;
                  no data → 0.5 (uncertain)
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.config.schema import PerformanceAssessorConfig
from rrr.models.enums import DimensionName, PerformanceTestStatus, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.performance import PerformanceInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import PerformanceSourceReader

_PERF_STATUS_SCORE: dict[PerformanceTestStatus, float] = {
    PerformanceTestStatus.PASSED: 1.0,
    # Not running a load test is uncertain — penalised but not a hard zero.
    PerformanceTestStatus.NOT_RUN: 0.5,
    PerformanceTestStatus.FAILED: 0.0,
}

# Capacity headroom at or above this percentage is considered fully healthy.
_CAPACITY_FULL_HEADROOM_PCT = 40.0

# Confidence is reduced when key data is absent (load test not run).
_CONFIDENCE_CAP_UNKNOWN = 0.75


def _latency_score(p99: float | None, threshold: float | None) -> float:
    """Map observed P99 latency relative to the SLO threshold to a [0, 1] score.

    Within the SLO (ratio ≤ 1.0) → 1.0. At exactly 2× the SLO or worse → 0.0.
    Linear between 1× and 2× so small overruns are not catastrophic. Returns
    0.5 (uncertain) when either value is absent.
    """
    if p99 is None or threshold is None or threshold == 0.0:
        return 0.5
    ratio = p99 / threshold
    # Clamp: below SLO is perfect (1.0); at 2× SLO or worse is zero.
    return max(0.0, min(1.0, 2.0 - ratio))


def _capacity_score(headroom_pct: float | None) -> float:
    """Map capacity headroom percentage to a [0, 1] score.

    ≥ 40 % headroom → 1.0 (plenty of room to absorb traffic spikes).
    0 % headroom → 0.0 (at capacity). Linear between 0 % and 40 %.
    Returns 0.5 (uncertain) when the value is absent.
    """
    if headroom_pct is None:
        return 0.5
    return min(1.0, headroom_pct / _CAPACITY_FULL_HEADROOM_PCT)


class PerformanceAssessor(BaseAssessor):
    """Gates release on load-test results, P99 latency vs SLO, and capacity headroom (ADR-0016).

    This dimension is gate-only (weight = 0 in WeightsConfig). It contributes no
    points to the weighted average but can veto a verdict to NO_GO or CONDITIONAL
    via the GateEngine when CRITICAL or MAJOR risk factors are raised (ADR-0013).
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        performance_reader: PerformanceSourceReader,
        performance_config: PerformanceAssessorConfig,
    ) -> None:
        """Wire the performance source reader and assessor config into the assessor."""
        super().__init__(runner, provider)
        self._reader = performance_reader
        self._config = performance_config

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.PERFORMANCE

    def _assess(self) -> DeterministicAssessment:
        """Compute performance posture from load-test outcome, latency, and capacity.

        CRITICAL risks (→ NO_GO cap via GateEngine): load test failed; P99 latency
        exceeds the SLO by the configured critical multiplier (default 2×).
        MAJOR risks (→ CONDITIONAL cap): any SLO breach; capacity headroom below
        the configured threshold (default 20 %).
        MINOR risk: load test has not been run (advisory signal, no cap).

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: PerformanceInput = self.invoke_tool(self._reader)

        perf_score = _PERF_STATUS_SCORE[data.performance_test_status]
        lat_score = _latency_score(data.p99_latency_ms, data.slo_p99_threshold_ms)
        cap_score = _capacity_score(data.capacity_headroom_pct)

        score = 0.5 * perf_score + 0.3 * lat_score + 0.2 * cap_score

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if data.performance_test_status is PerformanceTestStatus.FAILED:
            risks.append(
                RiskFactor(
                    description="Load / performance test failed — system did not meet NFR targets",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.PERFORMANCE,
                )
            )

        # Latency risks — only raised when both observed and threshold values are present.
        if data.p99_latency_ms is not None and data.slo_p99_threshold_ms is not None:
            ratio = data.p99_latency_ms / data.slo_p99_threshold_ms
            if ratio >= self._config.slo_critical_multiplier:
                risks.append(
                    RiskFactor(
                        description=(
                            f"P99 latency {data.p99_latency_ms:.0f} ms is "
                            f"{ratio:.1f}× the SLO threshold "
                            f"({data.slo_p99_threshold_ms:.0f} ms) — critical breach"
                        ),
                        severity=RiskSeverity.CRITICAL,
                        dimension=DimensionName.PERFORMANCE,
                    )
                )
            elif ratio > 1.0:
                risks.append(
                    RiskFactor(
                        description=(
                            f"P99 latency {data.p99_latency_ms:.0f} ms exceeds the SLO "
                            f"threshold ({data.slo_p99_threshold_ms:.0f} ms)"
                        ),
                        severity=RiskSeverity.MAJOR,
                        dimension=DimensionName.PERFORMANCE,
                    )
                )

        if (
            data.capacity_headroom_pct is not None
            and data.capacity_headroom_pct < self._config.low_capacity_threshold_pct
        ):
            risks.append(
                RiskFactor(
                    description=(
                        f"Capacity headroom {data.capacity_headroom_pct:.1f} % is below "
                        f"the minimum threshold ({self._config.low_capacity_threshold_pct:.0f} %)"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.PERFORMANCE,
                )
            )

        if data.performance_test_status is PerformanceTestStatus.NOT_RUN:
            risks.append(
                RiskFactor(
                    description="No load / performance test has been run for this release",
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.PERFORMANCE,
                )
            )
            # Incomplete evidence — reduce trust in the result.
            confidence_cap = _CONFIDENCE_CAP_UNKNOWN

        classification = self._classify(data, self._config)
        facts = [
            f"Load test: {data.performance_test_status.value}  ·  "
            f"P99 latency: {data.p99_latency_ms} ms  ·  "
            f"SLO threshold: {data.slo_p99_threshold_ms} ms  ·  "
            f"Capacity headroom: {data.capacity_headroom_pct} %"
        ]
        evidence = [
            self.build_evidence(
                "performance_score",
                round(score, 3),
                (
                    f"perf_status {perf_score:.2f}×0.5 + "
                    f"latency {lat_score:.2f}×0.3 + "
                    f"capacity {cap_score:.2f}×0.2"
                ),
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Performance posture {score * 100:.1f}%: "
            f"load_test={data.performance_test_status.value}, "
            f"p99={data.p99_latency_ms} ms, "
            f"slo={data.slo_p99_threshold_ms} ms, "
            f"headroom={data.capacity_headroom_pct} %."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["clear", "at_risk", "failed"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: PerformanceInput, config: PerformanceAssessorConfig) -> str:
        """Map load-test status and SLO/capacity data to an overall classification.

        ``failed``: load test failed, or P99 latency exceeds the critical SLO
        multiplier — the release is not safe to ship from a performance standpoint.
        ``at_risk``: SLO breach below the critical threshold, low capacity headroom,
        or no load test evidence at all — the release needs attention.
        ``clear``: load test passed with latency within SLO and adequate capacity.
        """
        if data.performance_test_status is PerformanceTestStatus.FAILED:
            return "failed"
        if (
            data.p99_latency_ms is not None
            and data.slo_p99_threshold_ms is not None
            and data.slo_p99_threshold_ms > 0.0
            and data.p99_latency_ms / data.slo_p99_threshold_ms >= config.slo_critical_multiplier
        ):
            return "failed"
        if (
            data.performance_test_status is PerformanceTestStatus.NOT_RUN
            or (
                data.p99_latency_ms is not None
                and data.slo_p99_threshold_ms is not None
                and data.p99_latency_ms > data.slo_p99_threshold_ms
            )
            or (
                data.capacity_headroom_pct is not None
                and data.capacity_headroom_pct < config.low_capacity_threshold_pct
            )
        ):
            return "at_risk"
        return "clear"
