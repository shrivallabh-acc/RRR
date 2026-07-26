"""``ObservabilityAssessor`` — monitoring, alerting, and tracing coverage (ADR-0016 item 7).

One of three assessors that supersede the old ``OperationalAssessor``. Weighted 0.03.

Score = alert_coverage × 0.35 + trace_coverage × 0.25 + log_coverage × 0.25
        + runbooks_linked × 0.15  (all expressed as 0-1 fractions from percentages).

Coverage scores are the primary signal. SLO definition and dashboard configuration
are checked as gate signals: missing SLO or no dashboards raises a MAJOR risk factor
(CONDITIONAL cap). The score itself is informational within the weighted total (0.03).
Confidence is capped when SLOs are not defined — the coverage metrics are less
meaningful without a baseline to measure against.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.observability import ObservabilityInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import ObservabilitySourceReader

# Sub-weights within this dimension — alert coverage is the dominant signal.
_ALERT_WEIGHT = 0.35
_TRACE_WEIGHT = 0.25
_LOG_WEIGHT = 0.25
_RUNBOOK_LINK_WEIGHT = 0.15

# Low coverage floor below which a MINOR advisory risk is raised.
_LOW_COVERAGE_FLOOR = 50.0

# Confidence is capped when SLO is undefined — coverage metrics lack a reference baseline.
_CONFIDENCE_CAP_NO_SLO = 0.75


class ObservabilityAssessor(BaseAssessor):
    """Scores monitoring, alerting, and tracing coverage (ADR-0016 item 7, weighted 0.03)."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        observability_reader: ObservabilitySourceReader,
    ) -> None:
        """Wire the observability source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = observability_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.OBSERVABILITY

    def _assess(self) -> DeterministicAssessment:
        """Compute the observability score from coverage metrics and SLO configuration.

        Combines alert, trace, log, and runbook-linkage coverage into a weighted
        score. Missing SLO definition or absent dashboards raise MAJOR risks.
        Low coverage (< 50%) on any metric raises an advisory MINOR risk.
        """
        data: ObservabilityInput = self.invoke_tool(self._reader)

        # Normalise percentages to [0, 1] for scoring.
        alert_score = data.alert_coverage_pct / 100.0
        trace_score = data.trace_coverage_pct / 100.0
        log_score = data.log_coverage_pct / 100.0
        runbook_link_score = data.runbooks_linked_to_alerts_pct / 100.0

        score = (
            _ALERT_WEIGHT * alert_score
            + _TRACE_WEIGHT * trace_score
            + _LOG_WEIGHT * log_score
            + _RUNBOOK_LINK_WEIGHT * runbook_link_score
        )

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if not data.dashboards_configured:
            risks.append(
                RiskFactor(
                    description="No monitoring dashboards configured for this release",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OBSERVABILITY,
                )
            )

        if not data.slo_defined:
            risks.append(
                RiskFactor(
                    description=(
                        "No Service Level Objectives defined"
                        " — release has no performance baseline"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OBSERVABILITY,
                )
            )
            # Coverage metrics are less meaningful without an SLO reference.
            confidence_cap = _CONFIDENCE_CAP_NO_SLO

        if data.slo_defined and not data.slo_alerts_configured:
            risks.append(
                RiskFactor(
                    description="SLOs are defined but no SLO budget-burn alerts are configured",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OBSERVABILITY,
                )
            )

        if data.alert_coverage_pct < _LOW_COVERAGE_FLOOR:
            risks.append(
                RiskFactor(
                    description=(
                        f"Alert coverage {data.alert_coverage_pct:.0f}%"
                        f" below the {_LOW_COVERAGE_FLOOR:.0f}% floor"
                    ),
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.OBSERVABILITY,
                )
            )

        if data.trace_coverage_pct < _LOW_COVERAGE_FLOOR:
            risks.append(
                RiskFactor(
                    description=(
                        f"Trace coverage {data.trace_coverage_pct:.0f}%"
                        f" below the {_LOW_COVERAGE_FLOOR:.0f}% floor"
                    ),
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.OBSERVABILITY,
                )
            )

        classification = self._classify(data)
        facts = [
            f"Alert: {data.alert_coverage_pct:.0f}%  ·  "
            f"Trace: {data.trace_coverage_pct:.0f}%  ·  "
            f"Log: {data.log_coverage_pct:.0f}%  ·  "
            f"Runbook-link: {data.runbooks_linked_to_alerts_pct:.0f}%  ·  "
            f"SLO: {'defined' if data.slo_defined else 'missing'}  ·  "
            f"Dashboards: {data.dashboards_count}"
        ]
        evidence = [
            self.build_evidence(
                "observability_score",
                round(score, 3),
                f"alert {alert_score:.2f}×{_ALERT_WEIGHT} + "
                f"trace {trace_score:.2f}×{_TRACE_WEIGHT} + "
                f"log {log_score:.2f}×{_LOG_WEIGHT} + "
                f"runbook_link {runbook_link_score:.2f}×{_RUNBOOK_LINK_WEIGHT}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Observability {score * 100:.1f}%: "
            f"alert={data.alert_coverage_pct:.0f}%, "
            f"trace={data.trace_coverage_pct:.0f}%, "
            f"log={data.log_coverage_pct:.0f}%, "
            f"slo={'ok' if data.slo_defined else 'missing'}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["good", "partial", "poor"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: ObservabilityInput) -> str:
        """Map SLO, dashboard, and coverage state to an observability classification.

        Good: SLO defined, dashboards configured, alerts active.
        Partial: any of the above is missing but not all.
        Poor: no SLO and no dashboards — release has no monitoring baseline.
        """
        if not data.slo_defined and not data.dashboards_configured:
            return "poor"
        if not data.slo_defined or not data.dashboards_configured or not data.slo_alerts_configured:
            return "partial"
        return "good"
