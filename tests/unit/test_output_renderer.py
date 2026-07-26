"""Tests for MarkdownRenderer, PlanRenderer, and HtmlRenderer (M2/M5, FR output quality)."""

from __future__ import annotations

from rrr.models.assessment import AssessmentOutputModel, AuditTrail
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, RiskSeverity, Verdict
from rrr.models.evidence import RiskFactor
from rrr.output import HtmlRenderer, MarkdownRenderer, PlanRenderer


def _go_result() -> AssessmentOutputModel:
    """Minimal GO verdict fixture for renderer tests."""
    return AssessmentOutputModel(
        release="RS-2026-Q2",
        value_stream="Retirement-Services",
        verdict=Verdict.GO,
        score=96,
        aggregate_confidence=0.92,
        dimensions=[
            DimensionResult(
                dimension=DimensionName.SCOPE,
                available=True,
                score=0.958,
                confidence=1.0,
                classification="delivered",
                narrative="230 of 240 SP closed.",
            ),
            DimensionResult(
                dimension=DimensionName.TEST_READINESS,
                available=True,
                score=0.953,
                confidence=1.0,
                classification="good",
                narrative="Suite pass rate 97%.",
            ),
        ],
        rationale="All dimensions above GO threshold with strong confidence.",
        remediation=["Monitor the 10 remaining open stories post-release."],
        risk_factors=[
            RiskFactor(description="10 stories not yet closed", severity=RiskSeverity.MINOR),
        ],
        audit_trail=AuditTrail(
            provider="RuleBasedProvider",
            effective_weights={DimensionName.SCOPE: 0.25, DimensionName.TEST_READINESS: 0.30},
        ),
    )


def _no_go_result() -> AssessmentOutputModel:
    """Minimal NO_GO fixture to exercise risk-factor and remediation sections."""
    return AssessmentOutputModel(
        release="RS-2026-Q1",
        value_stream="Retirement-Services",
        verdict=Verdict.NO_GO,
        score=32,
        dimensions=[
            DimensionResult(
                dimension=DimensionName.TEST_READINESS,
                available=True,
                score=0.31,
                confidence=0.8,
                classification="low",
                narrative="E2E pass rate 40%, below 50% floor.",
            ),
        ],
        rationale="E2E floor triggered NO_GO gate.",
        remediation=["Fix failing E2E suite before release.", "Re-run assessment after fixes."],
        risk_factors=[
            RiskFactor(
                description="E2E pass rate below critical floor",
                severity=RiskSeverity.CRITICAL,
                gate="e2e_critical_floor",
            ),
        ],
        audit_trail=AuditTrail(
            provider="RuleBasedProvider",
            gates_triggered=["e2e_critical_floor"],
        ),
    )


renderer = MarkdownRenderer()


def test_markdown_contains_release_name() -> None:
    md = renderer.render(_go_result())
    assert "RS-2026-Q2" in md


def test_markdown_contains_verdict_and_score() -> None:
    md = renderer.render(_go_result())
    assert "GO" in md
    assert "96" in md


def test_markdown_contains_dimension_table_header() -> None:
    md = renderer.render(_go_result())
    assert "Dimension" in md and "Score" in md and "Class" in md


def test_markdown_contains_dimension_rows() -> None:
    md = renderer.render(_go_result())
    assert "Scope" in md
    assert "Test Readiness" in md


def test_markdown_contains_rationale() -> None:
    md = renderer.render(_go_result())
    assert "All dimensions above GO threshold" in md


def test_markdown_contains_remediation_steps() -> None:
    md = renderer.render(_go_result())
    assert "Monitor the 10 remaining" in md


def test_markdown_contains_risk_factors() -> None:
    md = renderer.render(_go_result())
    assert "MINOR" in md.upper()
    assert "10 stories not yet closed" in md


def test_markdown_no_go_shows_critical_risk_and_gate() -> None:
    md = renderer.render(_no_go_result())
    assert "CRITICAL" in md.upper()
    assert "e2e_critical_floor" in md


def test_markdown_no_go_shows_gates_triggered() -> None:
    md = renderer.render(_no_go_result())
    assert "e2e_critical_floor" in md


def test_markdown_contains_audit_provider() -> None:
    md = renderer.render(_go_result())
    assert "RuleBasedProvider" in md


def test_markdown_unavailable_dimension_shows_warning() -> None:
    result = _go_result().model_copy(
        update={
            "dimensions": [
                DimensionResult(
                    dimension=DimensionName.ENVIRONMENT,
                    available=False,
                    score=0.0,
                    confidence=0.0,
                    narrative="Tool timed out.",
                )
            ]
        }
    )
    md = renderer.render(result)
    assert "Unavailable" in md


# ---------------------------------------------------------------------------
# PlanRenderer tests (M2 action-plan generator)
# ---------------------------------------------------------------------------

plan = PlanRenderer()


def test_plan_go_shows_cleared_message() -> None:
    md = plan.render(_go_result())
    assert "cleared" in md.lower() or "✅" in md


def test_plan_no_go_shows_blocked_message() -> None:
    md = plan.render(_no_go_result())
    assert "BLOCKED" in md or "blocked" in md.lower()


def test_plan_critical_risk_appears_in_blockers_section() -> None:
    md = plan.render(_no_go_result())
    assert "Blockers" in md
    assert "E2E pass rate below critical floor" in md


def test_plan_minor_risk_appears_in_recommended_section() -> None:
    md = plan.render(_go_result())
    assert "Recommended" in md
    assert "10 stories not yet closed" in md


def test_plan_remediation_steps_are_checkboxes() -> None:
    md = plan.render(_go_result())
    assert "- [ ] Monitor the 10 remaining" in md


def test_plan_no_go_remediation_checkboxes_present() -> None:
    md = plan.render(_no_go_result())
    assert "- [ ] Fix failing E2E suite" in md


def test_plan_gates_triggered_section_present() -> None:
    md = plan.render(_no_go_result())
    assert "Gates Triggered" in md
    assert "e2e_critical_floor" in md


def test_plan_unavailable_dimension_listed_for_reassessment() -> None:
    result = _go_result().model_copy(
        update={
            "dimensions": [
                DimensionResult(
                    dimension=DimensionName.ENVIRONMENT,
                    available=False,
                    score=0.0,
                    confidence=0.0,
                    narrative="Tool timed out.",
                )
            ]
        }
    )
    md = plan.render(result)
    assert "Re-Assessment" in md
    assert "Environment" in md


def test_plan_contains_rerun_instruction() -> None:
    md = plan.render(_go_result())
    assert "RS-2026-Q2" in md
    assert "rrr --release" in md


# ---------------------------------------------------------------------------
# HtmlRenderer tests (M5 HTML report)
# ---------------------------------------------------------------------------

html_renderer = HtmlRenderer()


def test_html_is_valid_doctype() -> None:
    html = html_renderer.render(_go_result())
    assert html.strip().lower().startswith("<!doctype html")


def test_html_contains_release_name() -> None:
    html = html_renderer.render(_go_result())
    assert "RS-2026-Q2" in html


def test_html_contains_verdict_label() -> None:
    html = html_renderer.render(_go_result())
    assert "GO" in html


def test_html_go_verdict_uses_success_badge() -> None:
    html = html_renderer.render(_go_result())
    assert "bg-success" in html


def test_html_no_go_verdict_uses_danger_badge() -> None:
    html = html_renderer.render(_no_go_result())
    assert "bg-danger" in html


def test_html_contains_score_value() -> None:
    html = html_renderer.render(_go_result())
    assert "96" in html


def test_html_contains_dimension_rows() -> None:
    html = html_renderer.render(_go_result())
    assert "Scope" in html
    assert "Test Readiness" in html


def test_html_contains_critical_risk_section() -> None:
    html = html_renderer.render(_no_go_result())
    assert "CRITICAL" in html
    assert "E2E pass rate below critical floor" in html


def test_html_contains_minor_risk_section() -> None:
    html = html_renderer.render(_go_result())
    assert "MINOR" in html
    assert "10 stories not yet closed" in html


def test_html_contains_remediation_steps() -> None:
    html = html_renderer.render(_go_result())
    assert "Monitor the 10 remaining" in html


def test_html_contains_audit_provider() -> None:
    html = html_renderer.render(_go_result())
    assert "RuleBasedProvider" in html


def test_html_unavailable_dimension_shows_warning_marker() -> None:
    result = _go_result().model_copy(
        update={
            "dimensions": [
                DimensionResult(
                    dimension=DimensionName.ENVIRONMENT,
                    available=False,
                    score=0.0,
                    confidence=0.0,
                    narrative="Tool timed out.",
                )
            ]
        }
    )
    html = html_renderer.render(result)
    assert "Unavailable" in html


def test_html_no_risk_factors_omits_risk_section() -> None:
    result = _go_result().model_copy(update={"risk_factors": []})
    html = html_renderer.render(result)
    # Risk section header should not appear when there are no risk factors.
    assert "Risk Factors" not in html
