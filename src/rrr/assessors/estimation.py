"""``EstimationAssessor`` — planned-value variance vs tolerance (FR-2, ADR-0012).

Deterministic core, from the latest snapshot's ``pv_latest {planned, actual}``:

* **Variance%** = ``((actual - planned) / planned) * 100``.
* **Classification** — over (variance < -tolerance), under (variance > +tolerance),
  within-tolerance otherwise. Default tolerance ±10%.
* **Score** = ``max(0, 100 - |variance%|) / 100``.

The brain extract pre-reduces PV to the latest point, so MAPE is just the absolute
variance of that point and the per-item / 3+-consecutive-run model does not apply
(ADR-0012). Estimation is a predictability signal, not a release-safety gate — its
out-of-tolerance risk is informational (no veto in ADR-0013).
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, EstimationClass, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.brain_reader import RKTBrainReader
from rrr.tools.runner import ToolRunner


class EstimationAssessor(BaseAssessor):
    """Scores estimation accuracy (planned vs actual) from the brain extract."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        brain_reader: RKTBrainReader,
        *,
        value_stream: str,
        snapshot: str = "latest",
        ir_name: str | None = None,
        tolerance: float = 0.10,
    ) -> None:
        super().__init__(runner, provider)
        self._reader = brain_reader
        self._value_stream = value_stream
        self._snapshot = snapshot
        self._ir_name = ir_name
        self._tolerance_pct = tolerance * 100

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.ESTIMATION

    def _assess(self) -> DeterministicAssessment:
        """Compute the estimation-accuracy score from the RKT brain snapshot.

        Reads planned vs actual story points for the release iteration, derives
        an accuracy ratio, and classifies it as OVER/WITHIN_TOLERANCE/UNDER.
        A high over-run or significant under-run both attract MAJOR risk factors.
        """
        result = self.invoke_tool(
            self._reader,
            value_stream=self._value_stream,
            snapshot=self._snapshot,
            ir_name=self._ir_name,
        )
        pv = result.release.pv_latest
        variance_pct = ((pv.actual - pv.planned) / pv.planned) * 100 if pv.planned else 0.0
        score = max(0.0, 100 - abs(variance_pct)) / 100
        classification = self._classify(variance_pct)

        evidence = [
            self.build_evidence(
                "pv_variance_pct",
                round(variance_pct, 2),
                f"actual {pv.actual} vs planned {pv.planned}",
                tool=self._reader.name,
            )
        ]
        tol = f"±{self._tolerance_pct:.0f}%"
        facts = [f"Earned-value variance {variance_pct:+.1f}% (tolerance {tol})."]
        risks: list[RiskFactor] = []
        if classification is not EstimationClass.WITHIN_TOLERANCE:
            direction = (
                "over-estimated" if classification is EstimationClass.OVER else "under-delivered"
            )
            risks.append(
                RiskFactor(
                    description=(
                        f"Estimation {direction}: variance {variance_pct:+.1f}% exceeds {tol}"
                    ),
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.ESTIMATION,
                )
            )

        summary_line = (
            f"Actual {pv.actual} vs planned {pv.planned} "
            f"(variance {variance_pct:+.1f}%) — {classification.value.replace('_', ' ')}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification.value,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=[c.value for c in EstimationClass],
        )

    def _classify(self, variance_pct: float) -> EstimationClass:
        """Map the variance percentage to an estimation class.

        OVER means actual < planned (team delivered less than expected — the budget
        was over-estimated). UNDER means actual > planned (team delivered more than
        planned — can indicate scope growth). WITHIN_TOLERANCE is the healthy band.
        The tolerance is symmetrical: default ±10% either side of planned.
        """
        if variance_pct < -self._tolerance_pct:
            return EstimationClass.OVER
        if variance_pct > self._tolerance_pct:
            return EstimationClass.UNDER
        return EstimationClass.WITHIN_TOLERANCE
