"""Pytest evaluation harness — asserts golden-dataset metrics meet the thresholds
defined in docs/evaluation-plan.md §6.  All metrics are deterministic (no LLM).

Structural quality tests (test_judge_*) verify the StructuralJudge populates
JudgeResult correctly.  Prose quality tests (test_prose_*) verify ProseQualityJudge
and ProseQualityResponse without live API calls (ClaudeProvider is mocked).
Report tests (test_report_*) verify EvalReportRenderer produces a valid Markdown
document for both the with-prose and without-prose cases.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tests.eval.judge import (
    JudgeResult,
    ProseQualityJudge,
    ProseQualityResponse,
    ProseQualityResult,
    StructuralJudge,
)
from tests.eval.metrics import EvalReport, evaluate_fixture
from tests.eval.report import EvalReportRenderer
from tests.eval.run_eval import FIXTURES, _overrides, run_prose_eval

from rrr.config import ConfigLoader
from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import Verdict

try:
    from rrr.pipeline import assess

    _PIPELINE_AVAILABLE = True
except ImportError:
    _PIPELINE_AVAILABLE = False

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason="rrr not installed"),
]


# ---------------------------------------------------------------------------
# Shared fixtures — pipeline runs once per module
# ---------------------------------------------------------------------------


@dataclass
class FullEvalOutput:
    """Combined result of one full evaluation pass (metrics + structural judge)."""

    report: EvalReport
    judge_results: list[JudgeResult] = field(default_factory=list)
    # Raw pipeline outputs kept for per-fixture judge assertions.
    raw_outputs: dict[str, AssessmentOutputModel] = field(default_factory=dict)


@pytest.fixture(scope="module")
def full_eval() -> FullEvalOutput:
    """Run the pipeline and both metric layers once per test module."""
    judge = StructuralJudge()
    report = EvalReport()
    judge_results: list[JudgeResult] = []
    raw_outputs: dict[str, AssessmentOutputModel] = {}

    for sample, release in FIXTURES:
        out = assess(ConfigLoader.load(overrides=_overrides(sample)), release=release)
        raw_outputs[sample] = out

        risk_descriptions = [
            r["description"] if isinstance(r, dict) else r.description for r in out.risk_factors
        ]
        result = evaluate_fixture(
            sample=sample,
            predicted_verdict=out.verdict,
            predicted_score=out.score,
            predicted_dims=[d.model_dump() for d in out.dimensions],
            predicted_risk_factors=risk_descriptions,
        )
        report.fixtures.append(result)
        judge_results.append(judge.judge(out, sample))

    return FullEvalOutput(report=report, judge_results=judge_results, raw_outputs=raw_outputs)


@pytest.fixture(scope="module")
def eval_report(full_eval: FullEvalOutput) -> EvalReport:
    """EvalReport derived from full_eval — backward-compatible with existing tests."""
    return full_eval.report


# ---------------------------------------------------------------------------
# Per-fixture verdict assertions (exact match — deterministic system)
# ---------------------------------------------------------------------------


EXPECTED_VERDICTS = {
    "g1_clean_release": Verdict.GO,
    "g2_failing_tests": Verdict.NO_GO,
    "g3_borderline": Verdict.CONDITIONAL,
    "g4_missing_data": Verdict.INCOMPLETE,
    "g5_scope_creep": Verdict.CONDITIONAL,
}


@pytest.mark.parametrize("sample,expected", EXPECTED_VERDICTS.items())
def test_verdict_matches_oracle(eval_report: EvalReport, sample: str, expected: Verdict) -> None:
    result = next(f for f in eval_report.fixtures if f.sample == sample)
    assert result.predicted_verdict == expected, (
        f"{sample}: expected {expected.value}, got {result.predicted_verdict.value}"
    )


# ---------------------------------------------------------------------------
# Per-fixture dimension-score tolerance (within ideal.json tolerance bands)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sample", [s for s, _ in FIXTURES])
def test_dimension_scores_within_tolerance(eval_report: EvalReport, sample: str) -> None:
    result = next(f for f in eval_report.fixtures if f.sample == sample)
    for dim, mae in result.dimension_maes.items():
        assert mae <= 0.03, f"{sample}/{dim}: MAE {mae:.4f} exceeds tolerance 0.03"


# ---------------------------------------------------------------------------
# Aggregate metric thresholds (evaluation-plan.md §6)
# ---------------------------------------------------------------------------


def test_verdict_macro_f1_meets_threshold(eval_report: EvalReport) -> None:
    assert eval_report.macro_f1 >= 0.80, f"Macro-F1 {eval_report.macro_f1:.3f} below threshold 0.80"


def test_mean_risk_f1_meets_threshold(eval_report: EvalReport) -> None:
    assert eval_report.mean_risk_f1 >= 0.70, (
        f"Mean risk-F1 {eval_report.mean_risk_f1:.3f} below threshold 0.70"
    )


def test_verdict_accuracy_is_100_pct(eval_report: EvalReport) -> None:
    assert eval_report.verdict_accuracy == 1.0, (
        f"Verdict accuracy {eval_report.verdict_accuracy:.2%} — "
        "expected 100% on deterministic system"
    )


# ---------------------------------------------------------------------------
# Structural judge — StructuralJudge.judge()
# ---------------------------------------------------------------------------


def test_judge_returns_one_result_per_fixture(full_eval: FullEvalOutput) -> None:
    assert len(full_eval.judge_results) == len(FIXTURES)


@pytest.mark.parametrize("sample", [s for s, _ in FIXTURES])
def test_judge_structural_score_in_valid_range(full_eval: FullEvalOutput, sample: str) -> None:
    result = next(j for j in full_eval.judge_results if j.sample == sample)
    assert 0.0 <= result.structural_score <= 1.0, (
        f"{sample}: structural_score {result.structural_score} out of [0, 1]"
    )


@pytest.mark.parametrize("sample", [s for s, _ in FIXTURES])
def test_judge_narrative_completeness_in_valid_range(
    full_eval: FullEvalOutput, sample: str
) -> None:
    result = next(j for j in full_eval.judge_results if j.sample == sample)
    assert 0.0 <= result.narrative_completeness <= 1.0


def test_judge_g1_risk_coverage_is_1_when_no_expected_risks(
    full_eval: FullEvalOutput,
) -> None:
    # g1_clean_release has no expected risk factors — coverage is vacuously 1.0.
    g1 = next(j for j in full_eval.judge_results if j.sample == "g1_clean_release")
    assert g1.ideal_risk_coverage == 1.0


@pytest.mark.parametrize("sample", [s for s, _ in FIXTURES])
def test_judge_all_fixtures_have_six_dimensions(full_eval: FullEvalOutput, sample: str) -> None:
    result = next(j for j in full_eval.judge_results if j.sample == sample)
    assert len(result.dimensions) == 6, (
        f"{sample}: expected 6 dimensions, got {len(result.dimensions)}"
    )


# ---------------------------------------------------------------------------
# ProseQualityResponse — model validation
# ---------------------------------------------------------------------------


def test_prose_quality_response_valid_construction() -> None:
    resp = ProseQualityResponse(
        clarity=0.8,
        specificity=0.7,
        actionability=0.6,
        evidence_grounding=0.9,
        overall=0.75,
    )
    assert resp.clarity == 0.8
    assert resp.overall == 0.75


def test_prose_quality_response_rejects_out_of_bounds() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ProseQualityResponse(
            clarity=1.5,  # > 1.0 — invalid
            specificity=0.5,
            actionability=0.5,
            evidence_grounding=0.5,
            overall=0.5,
        )


def test_prose_quality_response_rejects_negative() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ProseQualityResponse(
            clarity=0.5,
            specificity=-0.1,  # < 0.0 — invalid
            actionability=0.5,
            evidence_grounding=0.5,
            overall=0.5,
        )


def test_prose_quality_response_boundary_values() -> None:
    # 0.0 and 1.0 are inclusive boundary values — must be accepted.
    resp = ProseQualityResponse(
        clarity=0.0,
        specificity=1.0,
        actionability=0.0,
        evidence_grounding=1.0,
        overall=0.5,
    )
    assert resp.clarity == 0.0
    assert resp.specificity == 1.0


# ---------------------------------------------------------------------------
# ProseQualityJudge — is_available() and offline guard
# ---------------------------------------------------------------------------


def test_prose_judge_is_available_false_without_api_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        # Remove ANTHROPIC_API_KEY if present.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert ProseQualityJudge.is_available() is False


def test_run_prose_eval_returns_none_without_api_key(full_eval: FullEvalOutput) -> None:
    with patch("tests.eval.judge.ProseQualityJudge.is_available", return_value=False):
        result = run_prose_eval(full_eval.raw_outputs)
    assert result is None


# ---------------------------------------------------------------------------
# ProseQualityJudge — judge() with mocked ClaudeProvider
# ---------------------------------------------------------------------------


def _make_mock_response() -> ProseQualityResponse:
    """Return a fixed ProseQualityResponse for use in mock side_effects."""
    return ProseQualityResponse(
        clarity=0.80,
        specificity=0.75,
        actionability=0.70,
        evidence_grounding=0.85,
        overall=0.77,
    )


@pytest.fixture()
def prose_judge_with_mock_provider() -> ProseQualityJudge:
    """ProseQualityJudge with ClaudeProvider.__init__ bypassed."""
    with patch("tests.eval.judge.ProseQualityJudge.__init__", return_value=None):
        judge = ProseQualityJudge.__new__(ProseQualityJudge)
        mock_provider = MagicMock()
        mock_provider.reason.return_value = _make_mock_response()
        judge._provider = mock_provider
        return judge


def test_prose_judge_returns_result_for_fixture(
    prose_judge_with_mock_provider: ProseQualityJudge,
    full_eval: FullEvalOutput,
) -> None:
    sample = "g1_clean_release"
    out = full_eval.raw_outputs[sample]
    result = prose_judge_with_mock_provider.judge(out, sample)
    assert isinstance(result, ProseQualityResult)
    assert result.sample == sample


def test_prose_judge_mean_overall_in_valid_range(
    prose_judge_with_mock_provider: ProseQualityJudge,
    full_eval: FullEvalOutput,
) -> None:
    out = full_eval.raw_outputs["g1_clean_release"]
    result = prose_judge_with_mock_provider.judge(out, "g1_clean_release")
    assert 0.0 <= result.mean_overall <= 1.0


def test_prose_judge_scores_available_dimensions(
    prose_judge_with_mock_provider: ProseQualityJudge,
    full_eval: FullEvalOutput,
) -> None:
    # g1 has all dimensions available — expect dimension_scores to be non-empty.
    out = full_eval.raw_outputs["g1_clean_release"]
    result = prose_judge_with_mock_provider.judge(out, "g1_clean_release")
    assert len(result.dimension_scores) > 0


def test_prose_judge_scores_rationale(
    prose_judge_with_mock_provider: ProseQualityJudge,
    full_eval: FullEvalOutput,
) -> None:
    out = full_eval.raw_outputs["g1_clean_release"]
    result = prose_judge_with_mock_provider.judge(out, "g1_clean_release")
    # Rationale is present on g1 (RuleBasedProvider always writes one).
    assert result.rationale_score is not None
    assert 0.0 <= result.rationale_score.overall <= 1.0


def test_prose_judge_skips_unavailable_dimensions(
    prose_judge_with_mock_provider: ProseQualityJudge,
    full_eval: FullEvalOutput,
) -> None:
    # g4_missing_data has at least one unavailable dimension — provider must NOT
    # be called for it; the result should have fewer dimension_scores than g1.
    g4_out = full_eval.raw_outputs["g4_missing_data"]
    g1_out = full_eval.raw_outputs["g1_clean_release"]
    g4_result = prose_judge_with_mock_provider.judge(g4_out, "g4_missing_data")
    g1_result = prose_judge_with_mock_provider.judge(g1_out, "g1_clean_release")
    assert len(g4_result.dimension_scores) <= len(g1_result.dimension_scores)


def test_prose_judge_handles_provider_failure_gracefully(
    full_eval: FullEvalOutput,
) -> None:
    from rrr.errors import ProviderValidationError

    with patch("tests.eval.judge.ProseQualityJudge.__init__", return_value=None):
        judge = ProseQualityJudge.__new__(ProseQualityJudge)
        mock_provider = MagicMock()
        # All calls raise ProviderValidationError — judge must return a valid result.
        mock_provider.reason.side_effect = ProviderValidationError("test failure")
        judge._provider = mock_provider

    out = full_eval.raw_outputs["g1_clean_release"]
    result = judge.judge(out, "g1_clean_release")
    # Graceful degradation: empty scores, zero mean — no exception raised.
    assert result.dimension_scores == {}
    assert result.rationale_score is None
    assert result.mean_overall == 0.0


# ---------------------------------------------------------------------------
# Report renderer — EvalReportRenderer.render()
# ---------------------------------------------------------------------------


@pytest.fixture()
def rendered_report(full_eval: FullEvalOutput, tmp_path: Path) -> str:
    """Render the full eval report (no prose) to a temp file and return the content."""
    renderer = EvalReportRenderer()
    return renderer.render(full_eval.report, full_eval.judge_results, tmp_path / "eval-report.md")


@pytest.fixture()
def rendered_report_with_prose(
    full_eval: FullEvalOutput,
    prose_judge_with_mock_provider: ProseQualityJudge,
    tmp_path: Path,
) -> str:
    """Render the eval report with mocked prose results."""
    prose_results = [
        prose_judge_with_mock_provider.judge(full_eval.raw_outputs[s], s) for s, _ in FIXTURES
    ]
    renderer = EvalReportRenderer()
    return renderer.render(
        full_eval.report,
        full_eval.judge_results,
        tmp_path / "eval-report-prose.md",
        prose_results,
    )


def test_report_renderer_creates_file(full_eval: FullEvalOutput, tmp_path: Path) -> None:
    renderer = EvalReportRenderer()
    out_path = tmp_path / "eval-report.md"
    renderer.render(full_eval.report, full_eval.judge_results, out_path)
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_report_renderer_contains_all_section_headers(rendered_report: str) -> None:
    for header in [
        "# RRR Evaluation Report",
        "## 1. Deterministic Metrics Summary",
        "## 2. Per-Fixture Verdict Results",
        "## 3. Structural Quality",
        "## 4. Prose Quality",
        "## 5. Dimension Score MAE",
        "## 6. Quality Gate",
        "## Methodology",
    ]:
        assert header in rendered_report, f"Missing section: {header!r}"


def test_report_renderer_gate_shows_pass(rendered_report: str) -> None:
    # Deterministic pipeline on golden fixtures always achieves PASS.
    assert "✅ PASS" in rendered_report


def test_report_renderer_contains_all_fixture_names(rendered_report: str) -> None:
    for sample, _ in FIXTURES:
        assert sample in rendered_report, f"Fixture {sample!r} not found in report"


def test_report_renderer_prose_section_not_measured_without_results(
    rendered_report: str,
) -> None:
    # Without prose_results, the section should say 'Not measured'.
    assert "Not measured" in rendered_report


def test_report_renderer_prose_section_shows_scores_with_results(
    rendered_report_with_prose: str,
) -> None:
    # With prose_results, the section must contain numeric scores and all fixture names.
    assert "## 4. Prose Quality" in rendered_report_with_prose
    # Mean overall from mock (0.77) should appear.
    assert "0.77" in rendered_report_with_prose


def test_report_renderer_prose_gate_entry_present(rendered_report: str) -> None:
    # Gate section should note prose quality when results are absent.
    assert "ANTHROPIC_API_KEY absent" in rendered_report


def test_report_renderer_prose_gate_shows_score_when_present(
    rendered_report_with_prose: str,
) -> None:
    assert "Prose quality mean" in rendered_report_with_prose
