"""Tests for SecurityComplianceAssessor (ADR-0016, gate-only dimension).

Uses synthetic tmp_path stubs because the security dimension is opt-in and the
golden fixtures pre-date it. All scoring assertions derive from the documented
formula in the assessor module docstring.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.security import SecurityComplianceAssessor
from rrr.config.schema import SecurityAssessorConfig
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import SecuritySourceReader, ToolRunner

_DEFAULT_CONFIG = SecurityAssessorConfig(high_cve_threshold=5)


def _assessor(
    path: Path, cfg: SecurityAssessorConfig = _DEFAULT_CONFIG
) -> SecurityComplianceAssessor:
    return SecurityComplianceAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        SecuritySourceReader(path=str(path)),
        cfg,
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal security.json stub, merging caller fields over a clean baseline."""
    base = {
        "sast_status": "passed",
        "dast_status": "passed",
        "open_critical_cves": 0,
        "open_high_cves": 0,
        "license_approved": True,
        "data_privacy_approved": True,
        "pen_test_passed": True,
    }
    base.update(fields)
    p = tmp_path / "security.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (no risks) ------------------------------------------------------------------


def test_clean_posture_score_is_one(tmp_path: Path) -> None:
    """All scans passed, zero CVEs, all approvals granted → score = 1.0."""
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.SECURITY
    assert result.available is True
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "clear"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "security_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "security_score" in labels


# --- SAST / DAST failures → CRITICAL -----------------------------------------------------------


def test_sast_failed_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, sast_status="failed")).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("SAST" in rf.description for rf in critical)


def test_sast_failed_score_is_zero_plus_dast_half(tmp_path: Path) -> None:
    """sast=failed (0.0) × 0.5 + dast=passed (1.0) × 0.5 = 0.5."""
    result = _assessor(_stub(tmp_path, sast_status="failed")).assess()
    assert abs(result.score - 0.5) < 0.001
    assert result.classification == "failed"


def test_dast_failed_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, dast_status="failed")).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("DAST" in rf.description for rf in critical)


def test_both_scans_failed_score_is_zero(tmp_path: Path) -> None:
    """sast=failed (0.0) × 0.5 + dast=failed (0.0) × 0.5 = 0.0."""
    result = _assessor(_stub(tmp_path, sast_status="failed", dast_status="failed")).assess()
    assert result.score == 0.0
    assert result.classification == "failed"


# --- critical CVEs → CRITICAL ------------------------------------------------------------------


def test_open_critical_cves_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, open_critical_cves=2)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("critical CVE" in rf.description for rf in critical)
    assert result.classification == "failed"


def test_critical_cve_penalty_is_capped(tmp_path: Path) -> None:
    """10 critical CVEs × 0.20 would be 2.0 — penalty is capped at 0.60, score floors at 0."""
    result = _assessor(_stub(tmp_path, open_critical_cves=10)).assess()
    # 0.5 × 1.0 + 0.5 × 1.0 − 0.60 = 0.40
    assert abs(result.score - 0.40) < 0.001


# --- data privacy → CRITICAL -------------------------------------------------------------------


def test_data_privacy_not_approved_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, data_privacy_approved=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("privacy" in rf.description.lower() for rf in critical)
    assert result.classification == "failed"


# --- high CVEs → MAJOR -------------------------------------------------------------------------


def test_high_cves_at_threshold_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, open_high_cves=5)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("high-severity" in rf.description.lower() for rf in major)


def test_high_cves_below_threshold_no_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, open_high_cves=4)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert not any("high-severity CVE" in rf.description for rf in major)


def test_custom_high_cve_threshold_honoured(tmp_path: Path) -> None:
    cfg = SecurityAssessorConfig(high_cve_threshold=2)
    result = _assessor(_stub(tmp_path, open_high_cves=2), cfg=cfg).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("high-severity" in rf.description.lower() for rf in major)


# --- licence / pen-test → MAJOR / MINOR --------------------------------------------------------


def test_licence_not_approved_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, license_approved=False)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("licence" in rf.description.lower() for rf in major)


def test_pen_test_failed_raises_minor_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, pen_test_passed=False)).assess()
    minor = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert any("penetration" in rf.description.lower() for rf in minor)


def test_pen_test_not_run_raises_minor_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, pen_test_passed=None)).assess()
    minor = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert any("not been run" in rf.description.lower() for rf in minor)


# --- at_risk classification --------------------------------------------------------------------


def test_sast_not_run_is_at_risk(tmp_path: Path) -> None:
    """sast=not_run is uncertain — classified at_risk, not failed."""
    result = _assessor(_stub(tmp_path, sast_status="not_run")).assess()
    assert result.classification == "at_risk"


def test_dast_not_run_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, dast_status="not_run")).assess()
    assert result.classification == "at_risk"


def test_not_run_scans_reduce_confidence(tmp_path: Path) -> None:
    """Incomplete scan evidence — confidence should be capped to 0.75."""
    result = _assessor(_stub(tmp_path, sast_status="not_run")).assess()
    assert result.confidence <= 0.75


# --- missing file → unavailable ----------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.score == 0.0 and result.confidence == 0.0
    assert result.tool_invocations and result.tool_invocations[0].success is False


# --- classification helper unit tests ----------------------------------------------------------


def test_classify_clear_requires_both_scans_passed_and_approvals(tmp_path: Path) -> None:
    from rrr.models.security import SecurityInput

    data = SecurityInput(
        sast_status="passed",
        dast_status="passed",
        open_critical_cves=0,
        open_high_cves=0,
        license_approved=True,
        data_privacy_approved=True,
        pen_test_passed=True,
    )
    assert SecurityComplianceAssessor._classify(data) == "clear"


def test_classify_failed_when_sast_failed() -> None:
    from rrr.models.security import SecurityInput

    data = SecurityInput(sast_status="failed", dast_status="passed")
    assert SecurityComplianceAssessor._classify(data) == "failed"


def test_classify_at_risk_when_approvals_pending() -> None:
    from rrr.models.security import SecurityInput

    data = SecurityInput(
        sast_status="passed",
        dast_status="passed",
        data_privacy_approved=None,
    )
    assert SecurityComplianceAssessor._classify(data) == "at_risk"
