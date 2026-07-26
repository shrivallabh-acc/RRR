"""Structural and prose-quality judges for LLM-generated assessment outputs (FR-28, ADR-0008).

Two complementary judges:

* ``StructuralJudge`` — offline, CI-safe.  Checks that every field the LLM is
  responsible for (narrative, classification, rationale, remediation) is present and
  non-empty across all golden fixtures.  Works with any provider, including
  RuleBasedProvider, so it always runs in CI.

* ``ProseQualityJudge`` — live-LLM, optional (Phase 2).  Scores the clarity,
  specificity, actionability, and evidence-grounding of each dimension narrative and
  the verdict rationale using ClaudeProvider.  Returns ``None`` when
  ``ANTHROPIC_API_KEY`` is absent so CI stays green without a key.

Both judges are invoked by ``run_eval.py`` and their results are woven into the
Markdown evaluation report by ``report.py``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field

from rrr.models.assessment import AssessmentOutputModel
from rrr.models.base import RRRModel

logger = logging.getLogger(__name__)

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden"

# Default model for prose scoring — cheapest Haiku model keeps eval cost low.
_PROSE_QUALITY_MODEL = "claude-haiku-4-5-20251001"

# Instruction prepended to every prose-quality scoring call.
_SCORE_INSTRUCTION = (
    "You are a technical writing reviewer evaluating a release-readiness assessment narrative. "
    "Score the text on the four quality criteria defined in the JSON schema field descriptions. "
    "Each score is 0.0-1.0. "
    "For 'overall', compute: clarity*0.25 + specificity*0.30 + actionability*0.25 "
    "+ evidence_grounding*0.20. "
    "Base scores ONLY on the text provided — do not infer information that is not present. "
    "Return a JSON object with exactly the five numeric fields and no extra keys."
)


# ---------------------------------------------------------------------------
# Result types — Structural judge
# ---------------------------------------------------------------------------


@dataclass
class DimensionJudge:
    """Structural quality verdict for one dimension's LLM output fields."""

    dimension: str
    available: bool
    has_narrative: bool
    narrative_length: int
    has_classification: bool
    confidence_valid: bool
    risk_factor_count: int


@dataclass
class JudgeResult:
    """Aggregated structural quality score for one assessed golden fixture."""

    sample: str
    dimensions: list[DimensionJudge] = field(default_factory=list)
    has_rationale: bool = False
    rationale_length: int = 0
    remediation_count: int = 0
    # Fraction of available dimensions that have a non-empty narrative.
    narrative_completeness: float = 0.0
    # Fraction of ideal.json expected_risk_factors that appear in the output.
    ideal_risk_coverage: float = 0.0
    # Weighted composite of all structural checks (0 = hollow, 1 = fully populated).
    structural_score: float = 0.0


# ---------------------------------------------------------------------------
# Result types — Prose quality judge
# ---------------------------------------------------------------------------


class ProseQualityResponse(RRRModel):
    """LLM-scored prose quality for one narrative text (FR-28, ADR-0008).

    Returned by ClaudeProvider.reason() after scoring a dimension narrative or the
    verdict rationale.  All fields are validated to [0, 1] by Pydantic before use.
    """

    clarity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Clear, jargon-free language readable by a non-specialist "
            "(0=opaque or dense with unexplained terms, 1=crystal-clear prose)"
        ),
    )
    specificity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "References specific metrics, percentages, or named evidence from the assessment "
            "(0=entirely generic statements, 1=highly specific with numbers and named items)"
        ),
    )
    actionability: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Suggests concrete next steps or remediation actions "
            "(0=no guidance or vague suggestions, 1=specific actionable steps)"
        ),
    )
    evidence_grounding: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Claims are supported by cited observations or data rather than bare assertions "
            "(0=unsubstantiated assertions only, 1=every claim linked to cited evidence)"
        ),
    )
    overall: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Weighted composite: clarity×0.25 + specificity×0.30 + actionability×0.25 "
            "+ evidence_grounding×0.20  (0=poor quality, 1=excellent quality)"
        ),
    )


@dataclass
class ProseQualityResult:
    """Prose quality scores for one golden fixture's LLM-generated narratives (FR-28).

    ``dimension_scores`` is keyed by dimension name string (e.g. ``'scope'``).
    ``rationale_score`` scores the verdict rationale; ``None`` if the rationale was
    empty or the scoring call failed.  ``mean_overall`` averages across all scored
    items (dimensions + rationale).
    """

    sample: str
    dimension_scores: dict[str, ProseQualityResponse] = field(default_factory=dict)
    rationale_score: ProseQualityResponse | None = None
    mean_overall: float = 0.0


# ---------------------------------------------------------------------------
# Structural judge
# ---------------------------------------------------------------------------


class StructuralJudge:
    """Offline structural validator for LLM-generated assessment fields (ADR-0008).

    Scores each golden fixture on whether the LLM populated every required output
    field rather than whether the prose content is semantically correct.  A
    structural_score of 1.0 means every field was present; lower scores indicate
    missing or empty LLM output.

    Usage::

        judge = StructuralJudge()
        result: JudgeResult = judge.judge(assessment_output, "g1_clean_release")
    """

    def judge(self, out: AssessmentOutputModel, sample: str) -> JudgeResult:
        """Evaluate the structural quality of one assessed fixture.

        Loads ideal.json for *sample* to measure risk-factor coverage, then
        inspects every LLM-written field in *out* for presence and basic validity.

        :param out: Pipeline AssessmentOutputModel for this fixture.
        :param sample: Golden fixture directory name (e.g. ``'g1_clean_release'``).
        :returns: JudgeResult with per-dimension breakdown and aggregate scores.
        """
        ideal_risks = self._load_ideal_risks(sample)

        dim_results: list[DimensionJudge] = []
        for dim in out.dimensions:
            dj = DimensionJudge(
                dimension=dim.dimension.value,
                available=dim.available,
                has_narrative=bool(dim.narrative and dim.narrative.strip()),
                narrative_length=len(dim.narrative or ""),
                has_classification=bool(dim.classification and str(dim.classification).strip()),
                confidence_valid=0.0 <= dim.confidence <= 1.0,
                risk_factor_count=len(dim.risk_factors),
            )
            dim_results.append(dj)

        has_rationale = bool(out.rationale and out.rationale.strip())

        # Collect all surfaced risk-factor descriptions from every dimension + top level.
        all_predicted_risks: list[str] = [
            rf.description for dim in out.dimensions for rf in dim.risk_factors
        ] + [rf.description for rf in out.risk_factors]

        narrative_completeness = self._narrative_completeness(dim_results)
        ideal_risk_coverage = self._compute_risk_coverage(all_predicted_risks, ideal_risks)
        structural_score = self._compute_structural_score(
            dim_results, has_rationale, narrative_completeness
        )

        return JudgeResult(
            sample=sample,
            dimensions=dim_results,
            has_rationale=has_rationale,
            rationale_length=len(out.rationale or ""),
            remediation_count=len(out.remediation),
            narrative_completeness=narrative_completeness,
            ideal_risk_coverage=ideal_risk_coverage,
            structural_score=structural_score,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_ideal_risks(sample: str) -> list[str]:
        """Load expected risk factor descriptions from the golden ideal.json."""
        path = GOLDEN / sample / "ideal.json"
        ideal = json.loads(path.read_text(encoding="utf-8"))
        return ideal.get("expected_risk_factors", [])

    @staticmethod
    def _narrative_completeness(dim_results: list[DimensionJudge]) -> float:
        """Fraction of available dimensions that have a non-empty narrative."""
        available = [d for d in dim_results if d.available]
        if not available:
            # Vacuously complete when no dimensions were assessed.
            return 1.0
        return sum(1 for d in available if d.has_narrative) / len(available)

    @staticmethod
    def _compute_risk_coverage(predicted: list[str], expected: list[str]) -> float:
        """Fraction of expected risk factors surfaced by the predicted output.

        Uses substring overlap (same heuristic as metrics._risk_f1) so minor
        phrasing variation does not penalise coverage.  Returns 1.0 when no
        risks were expected — a clean fixture is vacuously fully covered.
        """
        if not expected:
            # No expected risks — vacuously covered.
            return 1.0
        if not predicted:
            return 0.0

        def _matches(exp: str, pred_list: list[str]) -> bool:
            e = exp.lower()
            return any(e in p.lower() or p.lower() in e for p in pred_list)

        matched = sum(1 for e in expected if _matches(e, predicted))
        return matched / len(expected)

    @staticmethod
    def _compute_structural_score(
        dim_results: list[DimensionJudge],
        has_rationale: bool,
        narrative_completeness: float,
    ) -> float:
        """Composite 0-1 structural quality score across all checks.

        Weights: narrative completeness 40%, rationale presence 20%,
        classification completeness 20%, confidence validity 20%.  Each
        component is a 0-1 fraction so the weighted sum stays in [0, 1].
        """
        available = [d for d in dim_results if d.available]

        classification_completeness = (
            sum(1 for d in available if d.has_classification) / len(available) if available else 1.0
        )
        confidence_completeness = (
            sum(1 for d in available if d.confidence_valid) / len(available) if available else 1.0
        )

        return (
            0.40 * narrative_completeness
            + 0.20 * (1.0 if has_rationale else 0.0)
            + 0.20 * classification_completeness
            + 0.20 * confidence_completeness
        )


# ---------------------------------------------------------------------------
# Prose quality judge
# ---------------------------------------------------------------------------


class ProseQualityJudge:
    """Live-LLM prose quality scorer for assessment narratives (FR-28, ADR-0008).

    Scores the clarity, specificity, actionability, and evidence-grounding of each
    available dimension narrative and the verdict rationale using ClaudeProvider.
    Call ``is_available()`` first — the judge silently skips unavailable narratives
    and returns a partial result rather than raising; the caller receives a valid
    ``ProseQualityResult`` regardless.

    Usage::

        if ProseQualityJudge.is_available():
            pjudge = ProseQualityJudge()
            result = pjudge.judge(assessment_output, "g1_clean_release")
    """

    def __init__(self, model: str = _PROSE_QUALITY_MODEL) -> None:
        """Instantiate the judge and create a ClaudeProvider for scoring.

        :param model: Anthropic model ID (default: ``claude-haiku-4-5-20251001``).
        :raises ConfigurationError: if the ``anthropic`` package is not installed or
            ``ANTHROPIC_API_KEY`` is absent.
        """
        from rrr.providers.claude import ClaudeProvider

        # Low max_tokens and temperature=0 keep scoring calls cheap and deterministic.
        self._provider = ClaudeProvider(
            model=model,
            max_tokens=256,
            temperature=0.0,
        )

    @staticmethod
    def is_available() -> bool:
        """Return True if both ANTHROPIC_API_KEY and the anthropic package are present."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic as _  # noqa: F401

            return True
        except ImportError:
            return False

    def judge(self, out: AssessmentOutputModel, sample: str) -> ProseQualityResult:
        """Score prose quality for all narratives in one golden fixture.

        Makes one ClaudeProvider call per available dimension narrative and one for
        the verdict rationale.  Each call is independent — a failed call is logged
        and skipped rather than propagating an exception so the overall result is
        always a valid (possibly partial) ``ProseQualityResult``.

        :param out: AssessmentOutputModel for the fixture.
        :param sample: Golden fixture directory name (e.g. ``'g1_clean_release'``).
        :returns: ProseQualityResult with per-dimension and rationale scores.
        """
        dim_scores: dict[str, ProseQualityResponse] = {}
        all_overalls: list[float] = []

        for dim in out.dimensions:
            if not dim.available or not (dim.narrative and dim.narrative.strip()):
                continue
            context = (
                f"{dim.dimension.value} dimension (classification: {dim.classification or 'none'})"
            )
            scored = self._score_narrative(dim.narrative, context)
            if scored is not None:
                dim_scores[dim.dimension.value] = scored
                all_overalls.append(scored.overall)

        rationale_score: ProseQualityResponse | None = None
        if out.rationale and out.rationale.strip():
            context = f"verdict rationale (verdict: {out.verdict.value})"
            rationale_score = self._score_narrative(out.rationale, context)
            if rationale_score is not None:
                all_overalls.append(rationale_score.overall)

        mean_overall = sum(all_overalls) / len(all_overalls) if all_overalls else 0.0

        return ProseQualityResult(
            sample=sample,
            dimension_scores=dim_scores,
            rationale_score=rationale_score,
            mean_overall=mean_overall,
        )

    def _score_narrative(self, text: str, context_hint: str) -> ProseQualityResponse | None:
        """Call ClaudeProvider to score one prose narrative.

        Builds a ReasoningRequest with the scoring instruction in ``summary`` and
        the narrative text in ``facts``.  A ProviderValidationError (repair exhausted
        or API error) is caught and logged — callers receive None rather than an
        exception so one bad call does not abort the whole eval pass.

        :param text: The narrative text to evaluate.
        :param context_hint: Short label describing what this text represents.
        :returns: ProseQualityResponse or None if the provider call failed.
        """
        from rrr.errors import ProviderValidationError
        from rrr.providers.base import ReasoningRequest

        request = ReasoningRequest(
            summary=_SCORE_INSTRUCTION,
            facts=[
                f"Context: {context_hint}",
                f"Narrative text to evaluate:\n{text}",
            ],
        )
        try:
            return self._provider.reason(request, ProseQualityResponse)  # type: ignore[return-value]
        except ProviderValidationError:
            # Repair exhausted or API error — skip rather than crashing the eval pass.
            logger.warning("ProseQualityJudge: scoring failed for context=%r", context_hint)
            return None
