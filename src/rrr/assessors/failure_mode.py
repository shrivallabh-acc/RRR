"""``FailureModeAssessor`` — resilience and failure-mode gate (ADR-0016 item 12).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score:
  0.25 × failure_modes_documented
  0.25 × circuit_breakers_configured
  0.25 × (chaos_pass_rate_pct / 100 if chaos_tests_run else 0)
  0.25 × graceful_degradation_tested

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.failure_mode import FailureModeInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import FailureModeSourceReader

_DOC_WEIGHT = 0.25
_CIRCUIT_WEIGHT = 0.25
_CHAOS_WEIGHT = 0.25
_DEGRADATION_WEIGHT = 0.25


class FailureModeAssessor(BaseAssessor):
    """Gates release on resilience engineering posture (ADR-0016 item 12).

    Undocumented failure modes and absent circuit breakers are CRITICAL because
    they mean the team cannot reason about or contain cascading failures in
    production. Low chaos test pass rates and missing graceful degradation are
    MAJOR — the system's failure handling has not been exercised under realistic
    fault conditions.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        failure_mode_reader: FailureModeSourceReader,
    ) -> None:
        """Wire the failure mode source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = failure_mode_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.FAILURE_MODE

    def _assess(self) -> DeterministicAssessment:
        """Compute resilience posture from failure-mode documentation and chaos testing.

        CRITICAL risks (→ NO_GO): failure modes undocumented or circuit breakers absent.
        MAJOR risks (→ CONDITIONAL): chaos pass rate below threshold or tests not run,
            or graceful degradation has not been validated.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: FailureModeInput = self.invoke_tool(self._reader)

        doc_score = 1.0 if data.failure_modes_documented else 0.0
        circuit_score = 1.0 if data.circuit_breakers_configured else 0.0
        chaos_score = (data.chaos_pass_rate_pct / 100.0) if data.chaos_tests_run else 0.0
        degradation_score = 1.0 if data.graceful_degradation_tested else 0.0

        score = (
            _DOC_WEIGHT * doc_score
            + _CIRCUIT_WEIGHT * circuit_score
            + _CHAOS_WEIGHT * chaos_score
            + _DEGRADATION_WEIGHT * degradation_score
        )

        risks: list[RiskFactor] = []

        if not data.failure_modes_documented:
            risks.append(
                RiskFactor(
                    description=(
                        "Failure modes for critical paths are not documented — "
                        "the team cannot systematically reason about cascading failures"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.FAILURE_MODE,
                )
            )

        if not data.circuit_breakers_configured:
            risks.append(
                RiskFactor(
                    description=(
                        "Circuit breakers are absent on external service calls — "
                        "a downstream failure can cascade and take down the release"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.FAILURE_MODE,
                )
            )

        if not data.chaos_tests_run:
            risks.append(
                RiskFactor(
                    description=(
                        "Chaos / fault-injection tests have not been run — "
                        "system resilience is unproven under real failure conditions"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.FAILURE_MODE,
                )
            )
        elif data.chaos_pass_rate_pct < data.chaos_pass_threshold_pct:
            risks.append(
                RiskFactor(
                    description=(
                        f"Chaos test pass rate {data.chaos_pass_rate_pct:.1f}% is below "
                        f"the {data.chaos_pass_threshold_pct:.1f}% threshold — "
                        "the system fails too many fault-injection experiments"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.FAILURE_MODE,
                )
            )

        if not data.graceful_degradation_tested:
            risks.append(
                RiskFactor(
                    description=(
                        "Graceful degradation has not been validated under simulated "
                        "dependency failures — partial-failure behaviour is unknown"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.FAILURE_MODE,
                )
            )

        classification = self._classify(data)
        facts = [
            f"Failure modes documented: {data.failure_modes_documented}  ·  "
            f"Circuit breakers: {data.circuit_breakers_configured}  ·  "
            f"Chaos tests run: {data.chaos_tests_run}  ·  "
            f"Chaos pass rate: {data.chaos_pass_rate_pct:.1f}%  ·  "
            f"Graceful degradation tested: {data.graceful_degradation_tested}  ·  "
            f"FMEA complete: {data.fmea_complete}"
        ]
        evidence = [
            self.build_evidence(
                "failure_mode_score",
                round(score, 3),
                f"doc {doc_score:.1f}×{_DOC_WEIGHT} + circuit {circuit_score:.1f}×{_CIRCUIT_WEIGHT}"
                f" + chaos {chaos_score:.2f}×{_CHAOS_WEIGHT}"
                f" + degradation {degradation_score:.1f}×{_DEGRADATION_WEIGHT}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Failure mode posture {score * 100:.1f}%: "
            f"documented={data.failure_modes_documented}, "
            f"circuit_breakers={data.circuit_breakers_configured}, "
            f"chaos_pass={data.chaos_pass_rate_pct:.1f}%."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["resilient", "at_risk", "not_resilient"],
        )

    @staticmethod
    def _classify(data: FailureModeInput) -> str:
        """Map resilience posture to a classification.

        ``not_resilient`` when failure modes are undocumented or circuit breakers absent.
        ``at_risk`` when chaos tests not run, pass rate low, or graceful degradation untested.
        ``resilient`` when all critical controls are in place and chaos tests pass.
        """
        if not data.failure_modes_documented or not data.circuit_breakers_configured:
            return "not_resilient"
        if (
            not data.chaos_tests_run
            or data.chaos_pass_rate_pct < data.chaos_pass_threshold_pct
            or not data.graceful_degradation_tested
        ):
            return "at_risk"
        return "resilient"
