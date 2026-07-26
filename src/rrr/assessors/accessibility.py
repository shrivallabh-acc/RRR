"""``AccessibilityAssessor`` — WCAG compliance gate (ADR-0016 item 8).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score = (1 − critical_penalty − major_penalty − minor_penalty) clamped to [0, 1].
  critical_penalty: 0.30 per critical violation (cap 0.90)
  major_penalty:    0.10 per major violation    (cap 0.50)
  minor_penalty:    0.02 per minor violation    (cap 0.20)

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.accessibility import AccessibilityInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import AccessibilitySourceReader

_CRITICAL_PENALTY = 0.30
_CRITICAL_CAP = 0.90
_MAJOR_PENALTY = 0.10
_MAJOR_CAP = 0.50
_MINOR_PENALTY = 0.02
_MINOR_CAP = 0.20

# Reduced confidence when automated scan was not run — result is incomplete evidence.
_CONFIDENCE_CAP_NO_SCAN = 0.70


class AccessibilityAssessor(BaseAssessor):
    """Gates release on WCAG accessibility compliance (ADR-0016 item 8).

    This dimension is gate-only (weight = 0 in WeightsConfig). Critical WCAG
    violations (barriers preventing access) veto the verdict to NO_GO; major
    violations cap it to CONDITIONAL. The gate is excluded for HOTFIX tier
    releases where accessibility review is not applicable.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        accessibility_reader: AccessibilitySourceReader,
    ) -> None:
        """Wire the accessibility source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = accessibility_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.ACCESSIBILITY

    def _assess(self) -> DeterministicAssessment:
        """Compute accessibility posture from WCAG scan results and manual review.

        CRITICAL risks (→ NO_GO): any critical WCAG violations detected.
        MAJOR risks (→ CONDITIONAL): major violations detected, or manual review
            was completed but did not pass.
        MINOR risk: minor violations present (advisory, no verdict cap).

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: AccessibilityInput = self.invoke_tool(self._reader)

        critical_penalty = min(data.critical_violations * _CRITICAL_PENALTY, _CRITICAL_CAP)
        major_penalty = min(data.major_violations * _MAJOR_PENALTY, _MAJOR_CAP)
        minor_penalty = min(data.minor_violations * _MINOR_PENALTY, _MINOR_CAP)
        score = max(1.0 - critical_penalty - major_penalty - minor_penalty, 0.0)

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if data.critical_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.critical_violations} critical WCAG {data.wcag_target_level} "
                        "violation(s) — accessibility barriers blocking users with disabilities"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ACCESSIBILITY,
                )
            )

        if data.major_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.major_violations} major WCAG {data.wcag_target_level} "
                        "violation(s) — significant accessibility barriers detected"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ACCESSIBILITY,
                )
            )

        if data.manual_review_complete and data.manual_review_passed is False:
            risks.append(
                RiskFactor(
                    description=(
                        "Manual accessibility review completed but did not pass "
                        f"WCAG {data.wcag_target_level} conformance"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ACCESSIBILITY,
                )
            )

        if data.minor_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.minor_violations} minor WCAG advisory violation(s) — "
                        "low impact, no verdict cap"
                    ),
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.ACCESSIBILITY,
                )
            )

        # No automated scan means incomplete evidence — reduce confidence.
        if data.pages_scanned == 0:
            confidence_cap = _CONFIDENCE_CAP_NO_SCAN

        classification = self._classify(data)
        facts = [
            f"WCAG level: {data.wcag_target_level}  ·  "
            f"Tool: {data.scan_tool or 'not specified'}  ·  "
            f"Pages scanned: {data.pages_scanned}  ·  "
            f"Critical: {data.critical_violations}  ·  "
            f"Major: {data.major_violations}  ·  "
            f"Minor: {data.minor_violations}  ·  "
            "Manual review: "
            + ("passed" if data.manual_review_passed
               else "not passed" if data.manual_review_complete
               else "not done")
        ]
        evidence = [
            self.build_evidence(
                "accessibility_score",
                round(score, 3),
                f"1.0 − crit_penalty {critical_penalty:.2f} "
                f"− major_penalty {major_penalty:.2f} "
                f"− minor_penalty {minor_penalty:.2f}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Accessibility posture {score * 100:.1f}%: "
            f"critical={data.critical_violations}, major={data.major_violations}, "
            f"minor={data.minor_violations}, target={data.wcag_target_level}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["compliant", "at_risk", "non_compliant"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: AccessibilityInput) -> str:
        """Map violation counts and manual review outcome to an accessibility classification.

        ``non_compliant`` when critical violations exist or manual review failed.
        ``at_risk`` when major violations exist or manual review is incomplete.
        ``compliant`` when zero critical/major violations and manual review passed (or N/A).
        """
        if data.critical_violations > 0 or (
            data.manual_review_complete and data.manual_review_passed is False
        ):
            return "non_compliant"
        if data.major_violations > 0 or not data.manual_review_complete:
            return "at_risk"
        return "compliant"
