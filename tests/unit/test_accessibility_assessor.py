"""Tests for AccessibilityAssessor (ADR-0016 item 8, gate-only dimension).

Uses synthetic tmp_path stubs. Scoring assertions derive from the penalty formula
documented in the assessor module docstring.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.accessibility import AccessibilityAssessor
from rrr.models.accessibility import AccessibilityInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import AccessibilitySourceReader, ToolRunner


def _assessor(path: Path) -> AccessibilityAssessor:
    return AccessibilityAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        AccessibilitySourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal accessibility.json stub, merging caller fields over a clean baseline."""
    base: dict[str, object] = {
        "wcag_target_level": "AA",
        "scan_tool": "axe",
        "pages_scanned": 42,
        "critical_violations": 0,
        "major_violations": 0,
        "minor_violations": 3,
        "manual_review_complete": True,
        "manual_review_passed": True,
    }
    base.update(fields)
    p = tmp_path / "accessibility.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (minor violations only, review passed) ----------------------------------------


def test_clean_posture_score_reflects_minor_penalty(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.ACCESSIBILITY
    assert result.available is True
    # 1.0 − min(3 × 0.02, 0.20) = 0.94
    assert abs(result.score - 0.94) < 0.001
    assert result.classification == "compliant"


def test_clean_posture_has_no_critical_or_major_risks(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.CRITICAL not in severities
    assert RiskSeverity.MAJOR not in severities


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "accessibility_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "accessibility_score" in labels


# --- critical violations → CRITICAL --------------------------------------------------------------


def test_critical_violation_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, critical_violations=1)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert critical
    assert any("critical" in rf.description.lower() for rf in critical)


def test_critical_violation_classification_is_non_compliant(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, critical_violations=1)).assess()
    assert result.classification == "non_compliant"


def test_critical_violation_score_applies_penalty(tmp_path: Path) -> None:
    # 1 critical (0.30) + 0 major + 0 minor = 0.70
    result = _assessor(_stub(tmp_path, critical_violations=1, minor_violations=0)).assess()
    assert abs(result.score - 0.70) < 0.001


# --- major violations → MAJOR --------------------------------------------------------------------


def test_major_violation_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, major_violations=2)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("major" in rf.description.lower() for rf in major)


def test_major_violation_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, major_violations=1, critical_violations=0)).assess()
    assert result.classification == "at_risk"


def test_manual_review_failed_raises_major_and_non_compliant(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            critical_violations=0,
            major_violations=0,
            manual_review_complete=True,
            manual_review_passed=False,
        )
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("manual" in rf.description.lower() for rf in major)
    assert result.classification == "non_compliant"


# --- confidence cap when no pages scanned --------------------------------------------------------


def test_pages_scanned_zero_caps_confidence(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, pages_scanned=0)).assess()
    assert result.confidence <= 0.70


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.ACCESSIBILITY


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_compliant_when_no_violations_and_review_passed() -> None:
    data = AccessibilityInput(
        critical_violations=0,
        major_violations=0,
        manual_review_complete=True,
        manual_review_passed=True,
    )
    assert AccessibilityAssessor._classify(data) == "compliant"


def test_classify_non_compliant_when_critical_violations() -> None:
    data = AccessibilityInput(critical_violations=2)
    assert AccessibilityAssessor._classify(data) == "non_compliant"


def test_classify_at_risk_when_review_not_complete() -> None:
    data = AccessibilityInput(
        critical_violations=0,
        major_violations=0,
        manual_review_complete=False,
    )
    assert AccessibilityAssessor._classify(data) == "at_risk"
