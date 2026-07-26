"""Tests for AuditabilityAssessor (ADR-0016 item 9, gate-only dimension).

Uses synthetic tmp_path stubs. Scoring assertions derive from the weighted-mean
formula (7 components, GDPR double-weighted) documented in the assessor module.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.auditability import AuditabilityAssessor
from rrr.models.auditability import AuditabilityInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import AuditabilitySourceReader, ToolRunner


def _assessor(path: Path) -> AuditabilityAssessor:
    return AuditabilityAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        AuditabilitySourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal auditability.json stub, merging caller fields over a clean baseline."""
    base: dict[str, object] = {
        "audit_logging_enabled": True,
        "regulated_events_logged": True,
        "audit_log_immutability_guaranteed": True,
        "data_retention_days": 2555,
        "gdpr_logging_compliant": True,
        "pii_access_logged": True,
        "audit_trail_tested": True,
    }
    base.update(fields)
    p = tmp_path / "auditability.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (all controls enabled) --------------------------------------------------------


def test_clean_posture_score_is_one(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.AUDITABILITY
    assert result.available is True
    # all 7 components = 1.0 → mean = 1.0
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "compliant"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "auditability_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "auditability_score" in labels


# --- audit_logging_enabled=False → CRITICAL ------------------------------------------------------


def test_logging_disabled_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, audit_logging_enabled=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("logging" in rf.description.lower() for rf in critical)


def test_logging_disabled_classification_is_non_compliant(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, audit_logging_enabled=False)).assess()
    assert result.classification == "non_compliant"


# --- pii_access_logged=False → CRITICAL ----------------------------------------------------------


def test_pii_not_logged_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, pii_access_logged=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("pii" in rf.description.lower() for rf in critical)


def test_pii_not_logged_classification_is_non_compliant(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, pii_access_logged=False)).assess()
    assert result.classification == "non_compliant"


# --- gdpr_logging_compliant=False → MAJOR --------------------------------------------------------


def test_gdpr_non_compliant_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, gdpr_logging_compliant=False)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("gdpr" in rf.description.lower() for rf in major)


def test_gdpr_non_compliant_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, gdpr_logging_compliant=False)).assess()
    assert result.classification == "at_risk"


# --- audit_trail_tested=False → MAJOR ------------------------------------------------------------


def test_trail_untested_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, audit_trail_tested=False)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("audit trail" in rf.description.lower() for rf in major)


# --- gdpr_logging_compliant=None → confidence cap ------------------------------------------------


def test_gdpr_pending_caps_confidence(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, gdpr_logging_compliant=None)).assess()
    assert result.confidence <= 0.70


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.AUDITABILITY


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_compliant_when_all_enabled() -> None:
    data = AuditabilityInput(
        audit_logging_enabled=True,
        pii_access_logged=True,
        gdpr_logging_compliant=True,
        audit_trail_tested=True,
    )
    assert AuditabilityAssessor._classify(data) == "compliant"


def test_classify_non_compliant_when_logging_disabled() -> None:
    data = AuditabilityInput(audit_logging_enabled=False, pii_access_logged=True)
    assert AuditabilityAssessor._classify(data) == "non_compliant"


def test_classify_at_risk_when_gdpr_pending() -> None:
    data = AuditabilityInput(
        audit_logging_enabled=True,
        pii_access_logged=True,
        gdpr_logging_compliant=None,
        audit_trail_tested=True,
    )
    assert AuditabilityAssessor._classify(data) == "at_risk"
