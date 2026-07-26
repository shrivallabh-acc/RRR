"""``DependencyAssessor`` — completion + integration validation (FR-5).

* **Score** = ``count(completion == complete AND integration == passed) / total``.
* **Per-dependency class** — blocking (``not_started`` OR integration ``failed``),
  at_risk (``in_progress`` AND ``not_validated``), on_track otherwise.
* **Risks → gates (ADR-0013):** integration ``failed`` → NO_GO (critical);
  ``not_started`` or at_risk → CONDITIONAL (major).
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.dependency import DependencyInput, DependencyItem
from rrr.models.enums import (
    DependencyClass,
    DependencyCompletion,
    DimensionName,
    IntegrationStatus,
    RiskSeverity,
)
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import DependencySourceReader


class DependencyAssessor(BaseAssessor):
    """Scores dependency readiness from a dependency source."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        dependency_reader: DependencySourceReader,
    ) -> None:
        super().__init__(runner, provider)
        self._reader = dependency_reader

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.DEPENDENCY

    def _assess(self) -> DeterministicAssessment:
        """Compute the dependency-readiness score from the integration source data.

        Scores each dependency as ready or not using _is_ready(), divides the
        count of ready dependencies by the total to get a 0-1 score, and emits
        CRITICAL/MAJOR risk factors for anything that would block the release.
        """
        data: DependencyInput = self.invoke_tool(self._reader)
        deps = data.dependencies
        ready = sum(1 for d in deps if self._is_ready(d))
        score = ready / len(deps)

        risks: list[RiskFactor] = []
        for d in deps:
            cls = self._classify_dep(d)
            if d.integration is IntegrationStatus.FAILED:
                risks.append(
                    self._risk(
                        f"{d.name} integration failed",
                        RiskSeverity.CRITICAL,
                        gate="dependency_failed",
                    )
                )
            elif cls is DependencyClass.BLOCKING:  # not_started
                risks.append(
                    self._risk(
                        f"{d.name} not started",
                        RiskSeverity.MAJOR,
                        gate="dependency_blocking",
                    )
                )
            elif cls is DependencyClass.AT_RISK:
                risks.append(
                    self._risk(
                        f"{d.name} in progress, integration not validated",
                        RiskSeverity.MAJOR,
                        gate="dependency_blocking",
                    )
                )

        classification = self._classify(deps)
        facts = [f"{ready} of {len(deps)} dependencies complete and integration-passed."]
        evidence = [
            self.build_evidence(
                "dependency_score",
                round(score, 3),
                f"{ready}/{len(deps)} complete+passed",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"{ready} of {len(deps)} dependencies ready ({score * 100:.1f}%) — {classification}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["ready", "at_risk", "not_ready"],
        )

    @staticmethod
    def _is_ready(d: DependencyItem) -> bool:
        """Return True only when a dependency is fully done AND its integration test passed.

        Both conditions must hold: work being complete but untested (not_validated)
        does not count as ready because the integration contract is unverified.
        """
        return (
            d.completion is DependencyCompletion.COMPLETE
            and d.integration is IntegrationStatus.PASSED
        )

    @staticmethod
    def _classify_dep(d: DependencyItem) -> DependencyClass:
        """Assign a risk class to a single dependency.

        BLOCKING: work hasn't started, or the integration test has already failed —
        either way the dependency cannot be relied on for release.
        AT_RISK: work is in progress but integration hasn't been validated yet —
        it might still slip.
        ON_TRACK: everything else (complete and passing, or complete and validated).
        """
        if (
            d.completion is DependencyCompletion.NOT_STARTED
            or d.integration is IntegrationStatus.FAILED
        ):
            return DependencyClass.BLOCKING
        if (
            d.completion is DependencyCompletion.IN_PROGRESS
            and d.integration is IntegrationStatus.NOT_VALIDATED
        ):
            return DependencyClass.AT_RISK
        return DependencyClass.ON_TRACK

    def _risk(
        self, description: str, severity: RiskSeverity, *, gate: str | None = None
    ) -> RiskFactor:
        """Create a dependency risk factor, pinning it to this dimension.

        The optional ``gate`` name links the risk to a named GatesConfig entry so the
        GateEngine resolves the verdict cap from config, not just from severity (ADR-0014).
        """
        return RiskFactor(
            description=description,
            severity=severity,
            dimension=DimensionName.DEPENDENCY,
            gate=gate,
        )

    def _classify(self, deps: list[DependencyItem]) -> str:
        """Classify the dependency set as a whole based on the worst single dependency.

        One BLOCKING dependency makes the set not_ready — a single failed integration
        can break the release. One AT_RISK dependency makes the set at_risk (amber).
        Only when every dependency is ON_TRACK do we call the set ready.
        """
        classes = [self._classify_dep(d) for d in deps]
        if DependencyClass.BLOCKING in classes:
            return "not_ready"
        if DependencyClass.AT_RISK in classes:
            return "at_risk"
        return "ready"
