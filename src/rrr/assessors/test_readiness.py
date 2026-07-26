"""``TestReadinessAssessor`` — weighted quality / defect-trend / E2E (FR-4, ADR-0012).

Composite of three brain-sourced sub-scores:

* **Quality** (default 0.4) = ``sq_avg / 3`` (0-3 scale); repos in ``sq_below_1`` are
  flagged as quality risks.
* **Defect trend** (0.3) = direction of ``defect_trend_last5`` — declining→1.0
  (improving), flat→0.5, rising→0.0. Open ``blocker``/``critical`` counts surface as
  risk factors (they trip the ADR-0013 gates).
* **E2E pass rate** (0.3) = ``passed / max(run, planned)``.  When ``run < planned``
  (unrun tests exist) the denominator is ``planned`` so partial execution is penalised
  proportionally rather than hidden behind a clean pass-rate.

**E2E-absent fallback (ADR-0012):** when ``e2e_latest`` is missing, drop the E2E
component, renormalize quality/defect (0.4/0.3 → 0.571/0.429), and cap confidence
at 0.5 so a partial assessment is scored honestly, not penalized to zero.

**Input-freshness guard (W5):** when ``freshness_max_age_days > 0`` and the brain
snapshot is older than that threshold, a MINOR risk factor is appended so operators
are alerted that the evidence may not reflect the current test state.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.brain import E2EPoint, ReleaseRecord
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import EvidenceRecord, RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.brain_reader import RKTBrainReader
from rrr.tools.runner import ToolRunner

_SQ_MAX = 3.0
_E2E_ABSENT_CONFIDENCE_CAP = 0.5
READY_THRESHOLD = 0.80
PARTIAL_THRESHOLD = 0.50


class TestReadinessAssessor(BaseAssessor):
    """Scores test readiness as a weighted composite from the brain extract."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        brain_reader: RKTBrainReader,
        *,
        value_stream: str,
        snapshot: str = "latest",
        ir_name: str | None = None,
        quality_weight: float = 0.4,
        defect_weight: float = 0.3,
        e2e_weight: float = 0.3,
        e2e_critical_floor: float = 0.50,
        freshness_max_age_days: int = 0,
    ) -> None:
        """Initialise with tool, provider, and tuning parameters.

        Args:
            freshness_max_age_days: Emit a MINOR risk if the brain snapshot is older
                than this many days. 0 disables the check (default — backward compat).
        """
        super().__init__(runner, provider)
        self._reader = brain_reader
        self._value_stream = value_stream
        self._snapshot = snapshot
        self._ir_name = ir_name
        self._qw = quality_weight
        self._dw = defect_weight
        self._ew = e2e_weight
        self._e2e_floor = e2e_critical_floor
        self._freshness_days = freshness_max_age_days

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.TEST_READINESS

    def _assess(self) -> DeterministicAssessment:
        """Run all sub-score computations and return a DeterministicAssessment.

        Reads the brain extract via the brain reader tool, computes quality / defect /
        E2E sub-scores, applies the unrun-test penalty (W5), checks data freshness (W5),
        and aggregates into a single weighted score.
        """
        result = self.invoke_tool(
            self._reader,
            value_stream=self._value_stream,
            snapshot=self._snapshot,
            ir_name=self._ir_name,
        )
        release = result.release
        quality = min(1.0, max(0.0, release.sq_avg / _SQ_MAX))
        defect = self._defect_trend_score(release.defect_trend_last5)

        facts: list[str] = []
        risks: list[RiskFactor] = []
        evidence = [
            self.build_evidence(
                "quality_sq_avg",
                round(quality, 3),
                f"sq_avg {release.sq_avg}/3",
                tool=self._reader.name,
            ),
            self.build_evidence(
                "defect_trend",
                defect,
                f"last5 {release.defect_trend_last5}",
                tool=self._reader.name,
            ),
        ]

        score, confidence_cap, e2e_label, e2e_score = self._composite(
            release.e2e_latest, quality, defect, evidence, facts
        )
        self._collect_risks(release, risks)
        if e2e_score is not None and e2e_score < self._e2e_floor:
            risks.append(
                RiskFactor(
                    description=(
                        f"E2E pass rate {e2e_score * 100:.0f}% below critical floor "
                        f"{self._e2e_floor * 100:.0f}%"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.TEST_READINESS,
                )
            )

        # Input-freshness guard (W5): warn if snapshot is stale.
        self._check_freshness(result.snapshot_date, risks, facts)

        classification = self._classify(score)
        subs = f"quality {quality:.2f}, defect-trend {defect:.2f}, e2e {e2e_label}"
        summary_line = f"Test readiness {score * 100:.1f}% ({subs}) — {classification}."
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["ready", "partially_ready", "not_ready"],
            confidence_cap=confidence_cap,
        )

    def _composite(
        self,
        e2e: E2EPoint | None,
        quality: float,
        defect: float,
        evidence: list[EvidenceRecord],
        facts: list[str],
    ) -> tuple[float, float | None, str, float | None]:
        """Return (score, confidence_cap, e2e_label, e2e_score), handling E2E-absent.

        **Unrun-test penalty (W5):** when ``passed + failed < planned``, the denominator
        is ``planned`` rather than ``run``.  This means unrun tests count as failures in
        the pass-rate calculation, preventing partial execution from inflating the score.
        """
        run = (e2e.passed + e2e.failed) if e2e is not None else 0
        if e2e is not None and run > 0:
            # Use planned as denominator when some tests did not run (W5 penalty).
            effective_total = max(run, e2e.planned)
            e2e_score = e2e.passed / effective_total
            coverage_note = (
                f"{e2e.passed}/{effective_total} passed"
                if effective_total > run
                else f"{e2e.passed}/{run} passed"
            )
            evidence.append(
                self.build_evidence(
                    "e2e_pass_rate",
                    round(e2e_score, 3),
                    coverage_note,
                    tool=self._reader.name,
                )
            )
            if run < e2e.planned:
                facts.append(
                    f"E2E coverage: {run} of {e2e.planned} planned tests run "
                    f"({run / e2e.planned:.0%}); pass rate penalised against planned total."
                )
            score = self._qw * quality + self._dw * defect + self._ew * e2e_score
            return score, None, f"{e2e_score:.2f}", e2e_score
        # E2E absent — renormalize quality/defect and cap confidence (ADR-0012)
        total = self._qw + self._dw
        score = (self._qw / total) * quality + (self._dw / total) * defect
        facts.append("E2E results absent — scored on quality+defect only (reduced confidence).")
        return score, _E2E_ABSENT_CONFIDENCE_CAP, "n/a", None

    def _check_freshness(
        self, snapshot_date: str, risks: list[RiskFactor], facts: list[str]
    ) -> None:
        """Append a MINOR risk if the brain snapshot is older than the freshness threshold.

        A stale snapshot means the E2E and defect data may not reflect the current
        branch state. This is advisory (MINOR) because the team may not have control
        over snapshot generation frequency.
        """
        if self._freshness_days <= 0:
            return
        try:
            snap = date.fromisoformat(snapshot_date)
        except ValueError:
            # Unparseable date — skip the check rather than crashing.
            return
        today = datetime.now(tz=UTC).date()
        age = (today - snap).days
        if age > self._freshness_days:
            facts.append(
                f"Brain snapshot is {age} days old (threshold: {self._freshness_days} days)."
            )
            risks.append(
                RiskFactor(
                    description=(
                        f"Brain snapshot {snapshot_date} is {age} days old "
                        f"(> {self._freshness_days}-day freshness threshold)"
                    ),
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.TEST_READINESS,
                )
            )

    def _collect_risks(self, release: ReleaseRecord, risks: list[RiskFactor]) -> None:
        """Append risk factors for open defects and low-quality repos.

        Blocker defects are release-stopping — they trigger the NO_GO gate via
        ``gate="blocker_defects"`` (ADR-0013/0014). Critical defects are serious
        but not automatically fatal — they land as MAJOR (CONDITIONAL gate).
        Repos below quality 1.0 are informational (MINOR) and do not cap the verdict.
        """
        sev = release.defects_open.by_severity
        if sev.blocker > 0:
            risks.append(
                RiskFactor(
                    description=f"{sev.blocker} open blocker defect(s)",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.TEST_READINESS,
                    gate="blocker_defects",
                )
            )
        if sev.critical > 0:
            risks.append(
                RiskFactor(
                    description=f"{sev.critical} open critical defect(s)",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.TEST_READINESS,
                )
            )
        below = release.sq_below_1
        if below:
            risks.append(
                RiskFactor(
                    description=f"{len(below)} repo(s) below quality 1.0: {', '.join(below)}",
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.TEST_READINESS,
                )
            )

    @staticmethod
    def _defect_trend_score(trend: list[int]) -> float:
        """Convert the last-5-week defect count list into a 0-1 score.

        We only care about direction: if the count is falling (fewer defects being
        found or opened) the trend is good → 1.0. Rising → 0.0. Flat or not enough
        data to judge → 0.5 (neutral). We compare first vs last to capture the
        overall direction across the window rather than just the latest step.
        """
        if len(trend) < 2:
            # Not enough history to determine direction — treat as neutral.
            return 0.5
        delta = trend[-1] - trend[0]
        if delta < 0:
            return 1.0  # Defects decreasing — good sign.
        if delta > 0:
            return 0.0  # Defects increasing — bad sign.
        return 0.5  # No change.

    @staticmethod
    def _classify(score: float) -> str:
        """Map a composite 0-1 score to a human-readable test-readiness label.

        READY means the suite is passing well enough to ship (80 %+ composite).
        PARTIALLY_READY is the amber zone where the team should investigate before
        shipping. NOT_READY means fewer than 50 % of the weighted sub-scores pass.
        """
        if score >= READY_THRESHOLD:
            return "ready"
        if score >= PARTIAL_THRESHOLD:
            return "partially_ready"
        return "not_ready"
