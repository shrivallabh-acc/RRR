"""Markdown evaluation report renderer for the golden-dataset eval harness (FR-28).

Combines deterministic metrics (EvalReport from metrics.py), structural quality
results (JudgeResult from judge.py), and optional prose quality results
(ProseQualityResult from judge.py) into a human-readable Markdown document.
Intended to be called from run_eval.py and emitted to docs/eval-report.md so it
is version-controlled alongside the code.

Metric definitions: docs/evaluation-plan.md §3 and §6.
ADR: adr/0008-evaluation-golden-dataset-llm-judge.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.eval.judge import JudgeResult, ProseQualityResult
from tests.eval.metrics import EvalReport


class EvalReportRenderer:
    """Renders a combined deterministic + structural + prose-quality Markdown eval report.

    Usage::

        renderer = EvalReportRenderer()
        renderer.render(report, judge_results, Path("docs/eval-report.md"), prose_results)
    """

    def render(
        self,
        report: EvalReport,
        judge_results: list[JudgeResult],
        path: Path,
        prose_results: list[ProseQualityResult] | None = None,
    ) -> str:
        """Write the eval report to *path* and return the rendered Markdown.

        Sections: header, deterministic metrics summary, per-fixture verdict table,
        structural quality table, prose quality table (when prose_results provided),
        dimension-score MAE table, quality gate result, and methodology note.

        :param report: Aggregated EvalReport from metrics.evaluate_fixture calls.
        :param judge_results: One JudgeResult per fixture from StructuralJudge.judge.
        :param path: Output file path; parent directories are created if absent.
        :param prose_results: Optional prose quality results from ProseQualityJudge;
            None when ANTHROPIC_API_KEY is absent (section shown as 'not measured').
        :returns: The rendered Markdown string (also written to *path*).
        """
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        sections: list[list[str]] = [
            self._header(ts),
            self._metrics_summary(report),
            self._verdict_table(report),
            self._structural_table(judge_results),
            self._prose_quality_table(prose_results),
            self._dimension_mae_table(report),
            self._gate_result(report, judge_results, prose_results),
            self._methodology_note(),
        ]

        content = "\n".join(line for section in sections for line in section) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return content

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    @staticmethod
    def _header(ts: str) -> list[str]:
        """Render the report title block with generation timestamp and links."""
        return [
            "# RRR Evaluation Report",
            "",
            f"> Generated: {ts}  ",
            "> Golden dataset: 5 fixtures (g1–g5)  ",
            "> Metric definitions: [docs/evaluation-plan.md](evaluation-plan.md)  ",
            "> ADR: [ADR-0008](../adr/0008-evaluation-golden-dataset-llm-judge.md)",
            "",
            "---",
            "",
        ]

    @staticmethod
    def _metrics_summary(report: EvalReport) -> list[str]:
        """Render the top-level deterministic metric table."""
        macro_ok = report.macro_f1 >= 0.80
        risk_ok = report.mean_risk_f1 >= 0.70
        acc_ok = report.verdict_accuracy == 1.0
        acc_icon = "✅" if acc_ok else "❌"
        macro_icon = "✅" if macro_ok else "❌"
        risk_icon = "✅" if risk_ok else "❌"

        return [
            "## 1. Deterministic Metrics Summary",
            "",
            "| Metric | Value | Threshold | Status |",
            "|--------|-------|-----------|--------|",
            f"| Verdict accuracy | {report.verdict_accuracy:.1%} | 100% | {acc_icon} |",
            f"| Macro-F1 | {report.macro_f1:.3f} | ≥ 0.80 | {macro_icon} |",
            f"| Mean score MAE | {report.mean_score_mae:.2f} | lower is better | ℹ |",
            f"| Mean risk-factor F1 | {report.mean_risk_f1:.3f} | ≥ 0.70 | {risk_icon} |",
            "",
        ]

    @staticmethod
    def _verdict_table(report: EvalReport) -> list[str]:
        """Render per-fixture verdict match and risk-factor F1 table."""
        lines: list[str] = [
            "## 2. Per-Fixture Verdict Results",
            "",
            "| Fixture | Ideal | Predicted | Match | Score MAE | Risk F1 |",
            "|---------|-------|-----------|-------|-----------|---------|",
        ]
        for f in report.fixtures:
            match = "✅" if f.predicted_verdict == f.ideal_verdict else "❌"
            mae_str = (
                str(abs((f.predicted_score or 0) - (f.ideal_score or 0)))
                if f.predicted_score is not None and f.ideal_score is not None
                else "—"
            )
            lines.append(
                f"| {f.sample} | {f.ideal_verdict.value} | {f.predicted_verdict.value} "
                f"| {match} | {mae_str} | {f.risk_f1:.2f} |"
            )
        lines.append("")
        return lines

    @staticmethod
    def _structural_table(judge_results: list[JudgeResult]) -> list[str]:
        """Render the structural quality table from StructuralJudge results."""
        if not judge_results:
            return [
                "## 3. Structural Quality (LLM Output)",
                "",
                "> Structural judge was not run.",
                "",
            ]

        lines: list[str] = [
            "## 3. Structural Quality (LLM Output)",
            "",
            "> Checks that narrative, classification, rationale, and remediation fields are",
            "> present and non-empty.  Runs offline with any provider.",
            "",
            "| Fixture | Narrative | Structural | Risk | Rationale | Remediation |",
            "|---------|-----------|------------|------|-----------|-------------|",
        ]
        for j in judge_results:
            rat = "✅" if j.has_rationale else "❌"
            lines.append(
                f"| {j.sample} | {j.narrative_completeness:.0%} "
                f"| {j.structural_score:.2f} | {j.ideal_risk_coverage:.0%} "
                f"| {rat} | {j.remediation_count} |"
            )

        avg_structural = sum(j.structural_score for j in judge_results) / len(judge_results)
        avg_coverage = sum(j.ideal_risk_coverage for j in judge_results) / len(judge_results)
        lines.append(
            f"| **Mean** | — | **{avg_structural:.2f}** | **{avg_coverage:.0%}** | — | — |"
        )
        lines.append("")
        return lines

    @staticmethod
    def _prose_quality_table(prose_results: list[ProseQualityResult] | None) -> list[str]:
        """Render the prose quality table from ProseQualityJudge results.

        Shows per-fixture mean scores for clarity, specificity, actionability,
        and evidence-grounding.  When prose_results is None (API key absent),
        the section notes that scoring is not available.
        """
        if prose_results is None:
            return [
                "## 4. Prose Quality (LLM Narrative)",
                "",
                "> Not measured — set `ANTHROPIC_API_KEY` to enable live prose scoring",
                "> (`pip install rrr[cloud]` + `export ANTHROPIC_API_KEY=...`).",
                "",
            ]

        lines: list[str] = [
            "## 4. Prose Quality (LLM Narrative)",
            "",
            "> Scores each dimension narrative and verdict rationale on four criteria",
            "> (0–1 each) using ClaudeProvider.  Requires `ANTHROPIC_API_KEY`.",
            "",
            "| Fixture | Clarity | Specificity | Actionability | Evidence | Overall | Dims |",
            "|---------|---------|-------------|---------------|----------|---------|------|",
        ]

        all_overalls: list[float] = []
        for p in prose_results:
            all_scores = list(p.dimension_scores.values())
            if p.rationale_score:
                all_scores.append(p.rationale_score)

            if not all_scores:
                lines.append(f"| {p.sample} | — | — | — | — | — | 0 |")
                continue

            avg_clarity = sum(s.clarity for s in all_scores) / len(all_scores)
            avg_specificity = sum(s.specificity for s in all_scores) / len(all_scores)
            avg_actionability = sum(s.actionability for s in all_scores) / len(all_scores)
            avg_evidence = sum(s.evidence_grounding for s in all_scores) / len(all_scores)
            lines.append(
                f"| {p.sample} | {avg_clarity:.2f} | {avg_specificity:.2f} "
                f"| {avg_actionability:.2f} | {avg_evidence:.2f} "
                f"| {p.mean_overall:.2f} | {len(p.dimension_scores)} |"
            )
            all_overalls.append(p.mean_overall)

        if all_overalls:
            grand_mean = sum(all_overalls) / len(all_overalls)
            lines.append(f"| **Mean** | — | — | — | — | **{grand_mean:.2f}** | — |")
        lines.append("")
        return lines

    @staticmethod
    def _dimension_mae_table(report: EvalReport) -> list[str]:
        """Render per-fixture dimension-score MAE breakdown."""
        cols = ["scope", "estimation", "environment", "test_readiness", "dependency"]
        lines: list[str] = [
            "## 5. Dimension Score MAE per Fixture",
            "",
            "| Fixture | scope | estimation | environment | test_readiness | dependency |",
            "|---------|-------|------------|-------------|----------------|-----------|",
        ]
        for f in report.fixtures:
            maes = f.dimension_maes
            cells = [f"{maes[d]:.4f}" if d in maes else "—" for d in cols]
            lines.append(f"| {f.sample} | {' | '.join(cells)} |")
        lines.append("")
        return lines

    @staticmethod
    def _gate_result(
        report: EvalReport,
        judge_results: list[JudgeResult],
        prose_results: list[ProseQualityResult] | None = None,
    ) -> list[str]:
        """Render the quality gate summary including the optional prose quality check."""
        macro_ok = report.macro_f1 >= 0.80
        risk_ok = report.mean_risk_f1 >= 0.70
        acc_ok = report.verdict_accuracy == 1.0

        structural_ok = (
            all(j.structural_score >= 0.60 for j in judge_results)
            if judge_results
            else True  # no judge results — don't fail the gate
        )

        overall = macro_ok and risk_ok and acc_ok and structural_ok

        lines: list[str] = [
            "## 6. Quality Gate",
            "",
            "| Check | Result |",
            "|-------|--------|",
            f"| Verdict accuracy = 100% | {'✅ PASS' if acc_ok else '❌ FAIL'} |",
            f"| Macro-F1 ≥ 0.80 | {'✅ PASS' if macro_ok else '❌ FAIL'} |",
            f"| Mean risk-F1 ≥ 0.70 | {'✅ PASS' if risk_ok else '❌ FAIL'} |",
        ]
        if judge_results:
            lines.append(
                f"| Structural score ≥ 0.60 (all fixtures) | "
                f"{'✅ PASS' if structural_ok else '❌ FAIL'} |"
            )

        # Prose gate — informational (threshold ≥ 0.70 mean overall); not hard-gating.
        if prose_results:
            mean_prose = sum(p.mean_overall for p in prose_results) / len(prose_results)
            prose_ok = mean_prose >= 0.70
            lines.append(
                f"| Prose quality mean ≥ 0.70 | "
                f"{'✅ PASS' if prose_ok else '❌ FAIL'} ({mean_prose:.2f}) |"
            )
        else:
            lines.append("| Prose quality | ℹ Not measured (ANTHROPIC_API_KEY absent) |")

        lines += [
            "",
            f"**Overall: {'✅ PASS' if overall else '❌ FAIL'}**",
            "",
        ]
        return lines

    @staticmethod
    def _methodology_note() -> list[str]:
        """Render the methodology footnote."""
        return [
            "---",
            "",
            "## Methodology",
            "",
            "**Deterministic metrics** (§1–2, §5) are pure math over the golden dataset — no LLM.",
            "**Structural quality** (§3) checks LLM-written fields are present and non-empty;",
            "runs offline with any provider (CI-safe).",
            "**Prose quality** (§4) scores the clarity, specificity, actionability, and",
            "evidence-grounding of each narrative using ClaudeProvider (FR-28, ADR-0008);",
            "requires `ANTHROPIC_API_KEY` — omitted when key is absent.",
            "See [ADR-0008](../adr/0008-evaluation-golden-dataset-llm-judge.md).",
            "",
        ]
