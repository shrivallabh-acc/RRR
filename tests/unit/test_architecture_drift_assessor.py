"""Tests for ArchitectureDriftAssessor (ADR-0016 item 16, gate-only dimension).

Uses synthetic tmp_path stubs. Score = (adr_compliance/100) × (1−drift) × pattern_factor;
banned technologies immediately zero the score. Approved deviations subtract from raw counts.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.architecture_drift import ArchitectureDriftAssessor
from rrr.models.architecture_drift import ArchitectureDriftInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import ArchitectureDriftSourceReader, ToolRunner


def _assessor(path: Path) -> ArchitectureDriftAssessor:
    return ArchitectureDriftAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        ArchitectureDriftSourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal architecture_drift.json stub, merging caller fields over a clean baseline."""
    base: dict[str, object] = {
        "baseline_version": "v1.4.0",
        "tool": "Backstage",
        "assessment_date": "2026-07-08",
        "adr_compliance_pct": 95.0,
        "banned_technologies_detected": 0,
        "unapproved_patterns": 0,
        "tech_standard_violations": 0,
        "drift_score": 0.05,
        "approved_deviations": 0,
        "drift_threshold": 0.20,
        "adr_compliance_threshold_pct": 80.0,
    }
    base.update(fields)
    p = tmp_path / "architecture_drift.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (aligned with baseline) -------------------------------------------------------


def test_clean_posture_score_near_expected(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.ARCHITECTURE_DRIFT
    assert result.available is True
    # 0.95 × (1 − 0.05) × 1.0 = 0.9025
    assert abs(result.score - 0.9025) < 0.001
    assert result.classification == "aligned"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "architecture_drift_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "architecture_drift_score" in labels


# --- banned technologies → CRITICAL, score=0 -----------------------------------------------------


def test_banned_technologies_raise_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, banned_technologies_detected=2)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("banned" in rf.description.lower() for rf in critical)


def test_banned_technologies_zeroes_score(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, banned_technologies_detected=1)).assess()
    assert result.score == 0.0
    assert result.classification == "diverged"


# --- ADR compliance below threshold → CRITICAL ---------------------------------------------------


def test_low_adr_compliance_raises_critical(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, adr_compliance_pct=75.0, adr_compliance_threshold_pct=80.0)
    ).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("adr compliance" in rf.description.lower() for rf in critical)


def test_low_adr_compliance_classification_is_diverged(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, adr_compliance_pct=70.0, adr_compliance_threshold_pct=80.0)
    ).assess()
    assert result.classification == "diverged"


# --- unapproved patterns (net) → MAJOR, drifting -------------------------------------------------


def test_unapproved_patterns_raise_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, unapproved_patterns=3, approved_deviations=0)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("unapproved" in rf.description.lower() for rf in major)


def test_unapproved_patterns_classification_is_drifting(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, unapproved_patterns=2, approved_deviations=0)).assess()
    assert result.classification == "drifting"


# --- approved deviations cancel out unapproved patterns ------------------------------------------


def test_approved_deviations_cancel_unapproved_patterns(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, unapproved_patterns=2, approved_deviations=2)
    ).assess()
    # net_unapproved = 0 → no MAJOR from patterns; drift=0.05 < 0.20 → aligned
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert not any("unapproved" in rf.description for rf in major)
    assert result.classification == "aligned"


# --- drift score above threshold → MAJOR ---------------------------------------------------------


def test_high_drift_score_raises_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, drift_score=0.25, drift_threshold=0.20)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("drift score" in rf.description.lower() for rf in major)


def test_high_drift_score_classification_is_drifting(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, drift_score=0.30, drift_threshold=0.20)).assess()
    assert result.classification == "drifting"


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.ARCHITECTURE_DRIFT


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_aligned_when_fully_compliant() -> None:
    data = ArchitectureDriftInput(
        adr_compliance_pct=95.0,
        adr_compliance_threshold_pct=80.0,
        banned_technologies_detected=0,
        drift_score=0.05,
        drift_threshold=0.20,
    )
    assert ArchitectureDriftAssessor._classify(data, 0) == "aligned"


def test_classify_diverged_when_banned_tech() -> None:
    data = ArchitectureDriftInput(
        banned_technologies_detected=1,
        adr_compliance_pct=90.0,
        adr_compliance_threshold_pct=80.0,
    )
    assert ArchitectureDriftAssessor._classify(data, 0) == "diverged"


def test_classify_drifting_when_unapproved_patterns() -> None:
    data = ArchitectureDriftInput(
        banned_technologies_detected=0,
        adr_compliance_pct=90.0,
        adr_compliance_threshold_pct=80.0,
        drift_score=0.05,
        drift_threshold=0.20,
    )
    assert ArchitectureDriftAssessor._classify(data, 2) == "drifting"
