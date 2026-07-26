"""Run the full golden-dataset evaluation and emit a Markdown report.

Usage::

    .venv/Scripts/python.exe -m tests.eval.run_eval
or (from repo root)::

    .venv/Scripts/python.exe tests/eval/run_eval.py

Runs all five golden fixtures through the pipeline, computes deterministic
metrics (metrics.py), structural quality (judge.StructuralJudge), and — when
ANTHROPIC_API_KEY is set — prose quality (judge.ProseQualityJudge).  Prints a
summary to stdout and writes docs/eval-report.md via report.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # makes `tests.eval.*` importable when run as a script

from tests.eval.judge import (  # noqa: E402
    JudgeResult,
    ProseQualityJudge,
    ProseQualityResult,
    StructuralJudge,
)
from tests.eval.metrics import EvalReport, evaluate_fixture  # noqa: E402
from tests.eval.report import EvalReportRenderer  # noqa: E402

from rrr.config import ConfigLoader  # noqa: E402
from rrr.models.assessment import AssessmentOutputModel  # noqa: E402
from rrr.pipeline import assess  # noqa: E402

GOLDEN = ROOT / "tests" / "golden"
REPORT_PATH = ROOT / "docs" / "eval-report.md"
VS = "Retirement-Services"

FIXTURES = [
    ("g1_clean_release", "Launch 36 - Unified Onboarding"),
    ("g2_failing_tests", "Launch 37 - Payments Hub"),
    ("g3_borderline", "Launch 38 - Advice Workbench"),
    ("g4_missing_data", "Launch 39 - Missing Data"),
    ("g5_scope_creep", "Launch 40 - Onboarding Plus"),
]


def _overrides(sample: str) -> dict:
    """Build source overrides pointing at a specific golden fixture directory."""
    inp = GOLDEN / sample / "inputs"
    return {
        "sources": {
            "brain": {"dir": str(inp / "brain"), "value_stream": VS},
            "environment": {"type": "file", "path": str(inp / "environment.json")},
            "dependency": {"type": "file", "path": str(inp / "dependency.json")},
            "operability": {"type": "file", "path": str(inp / "operability.json")},
        }
    }


def run_full_eval() -> tuple[EvalReport, list[JudgeResult], list[ProseQualityResult] | None]:
    """Run all golden fixtures through the pipeline and return all three metric sets.

    Runs assess() once per fixture; computes deterministic metrics via
    evaluate_fixture(), structural quality via StructuralJudge, and prose quality
    via ProseQualityJudge (only when ANTHROPIC_API_KEY is set).

    :returns: ``(EvalReport, list[JudgeResult], list[ProseQualityResult] | None)`` —
        one entry per fixture in each list; prose results are None when the API key
        is absent so CI stays green without an Anthropic account.
    """
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

    prose_results = run_prose_eval(raw_outputs)

    return report, judge_results, prose_results


def run_prose_eval(
    outputs: dict[str, AssessmentOutputModel],
) -> list[ProseQualityResult] | None:
    """Score prose quality for all fixtures if ANTHROPIC_API_KEY is set.

    Scores the verdict rationale and available dimension narratives for each
    fixture using ClaudeProvider.  Returns None (not an empty list) when the
    judge is unavailable — callers treat None as 'not measured' rather than
    'all failed'.

    :param outputs: Map of fixture sample name → AssessmentOutputModel from
        the pipeline run.
    :returns: One ProseQualityResult per fixture, or None if unavailable.
    """
    if not ProseQualityJudge.is_available():
        return None
    pjudge = ProseQualityJudge()
    return [pjudge.judge(out, sample) for sample, out in outputs.items()]


def run_eval() -> EvalReport:
    """Run the golden-dataset evaluation and return deterministic metrics only.

    Convenience wrapper over run_full_eval() for callers that need only the
    EvalReport (e.g. test_eval.py's module-scoped fixture).
    """
    report, _, _ = run_full_eval()
    return report


def print_report(
    report: EvalReport,
    judge_results: list[JudgeResult] | None = None,
    prose_results: list[ProseQualityResult] | None = None,
) -> None:
    """Print a human-readable evaluation summary to stdout."""
    print("\n" + "=" * 65)
    print("RRR GOLDEN DATASET EVALUATION REPORT")
    print("=" * 65)

    print(f"\n{'Sample':<25} {'Ideal':<12} {'Predicted':<12} {'Match':<6} {'RiskF1':<8}")
    print("-" * 65)
    for f in report.fixtures:
        match = "✓" if f.predicted_verdict == f.ideal_verdict else "✗"
        print(
            f"{f.sample:<25} {f.ideal_verdict.value:<12} {f.predicted_verdict.value:<12} "
            f"{match:<6} {f.risk_f1:.2f}"
        )

    print("\n--- Aggregate Metrics ---")
    print(f"Verdict Accuracy : {report.verdict_accuracy:.2%}")
    print(f"Macro-F1         : {report.macro_f1:.3f}   (threshold ≥ 0.80)")
    print(f"Mean Score MAE   : {report.mean_score_mae:.2f}  (lower = better)")
    print(f"Mean Risk F1     : {report.mean_risk_f1:.3f}  (threshold ≥ 0.70)")

    print("\n--- Dimension Score MAE per Fixture ---")
    for f in report.fixtures:
        if f.dimension_maes:
            maes_str = "  ".join(f"{d}:{v:.3f}" for d, v in sorted(f.dimension_maes.items()))
            print(f"  {f.sample}: {maes_str}")

    if judge_results:
        print("\n--- Structural Quality ---")
        print(f"{'Sample':<25} {'Narrative':<12} {'Structural':<12} {'RiskCov':<10} {'Rationale'}")
        print("-" * 65)
        for j in judge_results:
            rat = "✓" if j.has_rationale else "✗"
            print(
                f"{j.sample:<25} {j.narrative_completeness:.0%}{'':>9} "
                f"{j.structural_score:.2f}{'':>9} "
                f"{j.ideal_risk_coverage:.0%}{'':>7} {rat}"
            )
        avg_s = sum(j.structural_score for j in judge_results) / len(judge_results)
        print(f"  Mean structural score: {avg_s:.2f}")

    if prose_results:
        print("\n--- Prose Quality (live LLM) ---")
        print(f"{'Sample':<25} {'Mean Overall':<14} {'Rationale':<12} {'Dims scored'}")
        print("-" * 65)
        for p in prose_results:
            rat_score = f"{p.rationale_score.overall:.2f}" if p.rationale_score else "—"
            print(
                f"{p.sample:<25} {p.mean_overall:.2f}{'':>11} "
                f"{rat_score:<12} {len(p.dimension_scores)}"
            )
        avg_p = sum(p.mean_overall for p in prose_results) / len(prose_results)
        print(f"  Mean prose overall: {avg_p:.2f}  (target ≥ 0.70)")
    else:
        print("\n--- Prose Quality ---")
        print("  [not measured — set ANTHROPIC_API_KEY to enable]")

    macro_ok = report.macro_f1 >= 0.80
    risk_ok = report.mean_risk_f1 >= 0.70
    print(
        f"\n{'PASS' if macro_ok and risk_ok else 'FAIL'} "
        f"(macro-F1 {'✓' if macro_ok else '✗'}  risk-F1 {'✓' if risk_ok else '✗'})"
    )


if __name__ == "__main__":
    full_report, jr, pr = run_full_eval()
    print_report(full_report, jr, pr)
    EvalReportRenderer().render(full_report, jr, REPORT_PATH, pr)
    print(f"\nMarkdown report written to: {REPORT_PATH}")
