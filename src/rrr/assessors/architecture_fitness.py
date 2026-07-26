"""``ArchitectureFitnessAssessor`` — automated architecture test gate (ADR-0016 item 15).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score = tests_passed / tests_run  (0 if no tests run, 1 if all pass).
Deductions for structural violations:
  layering / banned-dependency violations → CRITICAL (structural rules broken)
  coupling violations / failing tests → MAJOR (quality signal, not structural)

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.architecture_fitness import ArchitectureFitnessInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import ArchitectureFitnessSourceReader

# Reduced confidence when no fitness functions have been defined or run.
_CONFIDENCE_CAP_NO_TESTS = 0.65


class ArchitectureFitnessAssessor(BaseAssessor):
    """Gates release on architecture fitness function results (ADR-0016 item 15).

    Layering violations (e.g. UI → repository) and banned-dependency violations
    are CRITICAL because they indicate the codebase has broken fundamental
    architectural rules that compromise maintainability and security boundaries.
    Coupling violations and failing fitness tests are MAJOR — they indicate
    architectural degradation that will compound if not addressed before release.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        fitness_reader: ArchitectureFitnessSourceReader,
    ) -> None:
        """Wire the architecture fitness source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = fitness_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.ARCHITECTURE_FITNESS

    def _assess(self) -> DeterministicAssessment:
        """Compute architecture fitness from test results and violation counts.

        CRITICAL risks (→ NO_GO): layering or banned-dependency violations detected.
        MAJOR risks (→ CONDITIONAL): coupling violations or fitness tests failing.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: ArchitectureFitnessInput = self.invoke_tool(self._reader)

        # Pass rate is the primary score signal; violations are the gate signal.
        score = (
            data.tests_passed / data.tests_run
            if data.tests_run > 0
            else 0.0
        )

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if data.layering_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.layering_violations} layering violation(s) detected — "
                        "calls that skip architectural layers break bounded-context isolation"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ARCHITECTURE_FITNESS,
                )
            )

        if data.banned_dependency_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.banned_dependency_violations} banned-dependency violation(s) — "
                        "references to explicitly prohibited packages or modules"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ARCHITECTURE_FITNESS,
                )
            )

        if data.coupling_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.coupling_violations} coupling violation(s) — "
                        "dependencies between components that violate the coupling rules"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ARCHITECTURE_FITNESS,
                )
            )

        if data.tests_failed > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.tests_failed} of {data.tests_run} architecture fitness "
                        "test(s) failed — architectural constraints are not being enforced"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ARCHITECTURE_FITNESS,
                )
            )

        # No tests defined or run — evidence is absent; reduce confidence.
        if data.tests_run == 0 or data.fitness_functions_defined == 0:
            confidence_cap = _CONFIDENCE_CAP_NO_TESTS

        classification = self._classify(data)
        top_violations = data.violations[:3]  # summarise first 3 for the facts line
        facts = [
            f"Tool: {data.tool or 'not specified'}  ·  "
            f"Tests run/passed/failed: {data.tests_run}/{data.tests_passed}/{data.tests_failed}  ·"
            "  "
            f"Layering violations: {data.layering_violations}  ·  "
            f"Banned-dep violations: {data.banned_dependency_violations}  ·  "
            f"Coupling violations: {data.coupling_violations}"
        ]
        if top_violations:
            facts.append(f"Top violations: {'; '.join(top_violations)}")
        evidence = [
            self.build_evidence(
                "architecture_fitness_score",
                round(score, 3),
                f"{data.tests_passed}/{data.tests_run} tests passed"
                if data.tests_run > 0 else "no tests run",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Architecture fitness posture {score * 100:.1f}%: "
            f"passed={data.tests_passed}/{data.tests_run}, "
            f"layering={data.layering_violations}, "
            f"coupling={data.coupling_violations}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["compliant", "at_risk", "violated"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: ArchitectureFitnessInput) -> str:
        """Map fitness test results and violations to an architecture fitness classification.

        ``violated`` when layering or banned-dependency violations are present.
        ``at_risk`` when coupling violations exist or fitness tests fail.
        ``compliant`` when all tests pass and no violations are detected.
        """
        if data.layering_violations > 0 or data.banned_dependency_violations > 0:
            return "violated"
        if data.coupling_violations > 0 or data.tests_failed > 0:
            return "at_risk"
        return "compliant"
