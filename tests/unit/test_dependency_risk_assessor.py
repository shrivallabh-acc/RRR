"""Tests for DependencyRiskAssessor (ADR-0016 item 13, gate-only dimension).

Uses synthetic tmp_path stubs. Any malicious package immediately zeroes the score.
Critical transitive CVEs and supply-chain violations drive the verdict caps.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.dependency_risk import DependencyRiskAssessor
from rrr.models.dependency_risk import DependencyRiskInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import DependencyRiskSourceReader, ToolRunner


def _assessor(path: Path) -> DependencyRiskAssessor:
    return DependencyRiskAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        DependencyRiskSourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal dependency_risk.json stub, merging caller fields over a clean baseline."""
    base: dict[str, object] = {
        "sca_tool": "Snyk",
        "sca_scan_date": "2026-07-08",
        "eol_dependencies_count": 0,
        "critical_transitive_cves": 0,
        "high_transitive_cves": 3,
        "supply_chain_violations": 0,
        "pinned_dependencies_pct": 98.5,
        "known_malicious_packages": 0,
        "high_transitive_cve_threshold": 10,
    }
    base.update(fields)
    p = tmp_path / "dependency_risk.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (no critical signals) ---------------------------------------------------------


def test_clean_posture_score_is_one(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.DEPENDENCY_RISK
    assert result.available is True
    # high_cves=3 < threshold=10 → no high penalty; all other counts=0 → score=1.0
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "clean"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "dependency_risk_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "dependency_risk_score" in labels


# --- malicious packages → CRITICAL, score=0 ------------------------------------------------------


def test_malicious_package_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, known_malicious_packages=1)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("malicious" in rf.description.lower() for rf in critical)


def test_malicious_package_zeroes_score(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, known_malicious_packages=2)).assess()
    assert result.score == 0.0
    assert result.classification == "compromised"


# --- critical transitive CVEs → CRITICAL ---------------------------------------------------------


def test_critical_transitive_cves_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, critical_transitive_cves=1)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("critical" in rf.description.lower() and "cve" in rf.description.lower()
               for rf in critical)


def test_critical_transitive_cves_classification_is_compromised(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, critical_transitive_cves=2)).assess()
    assert result.classification == "compromised"
    # 2 × 0.25 = 0.50 penalty → score = 0.50
    assert abs(result.score - 0.50) < 0.001


# --- supply chain violations → MAJOR -------------------------------------------------------------


def test_supply_chain_violations_raise_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, supply_chain_violations=2)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("supply-chain" in rf.description.lower() or "supply chain" in rf.description.lower()
               for rf in major)


def test_supply_chain_violations_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, supply_chain_violations=1)).assess()
    assert result.classification == "at_risk"


# --- high transitive CVEs above threshold → MAJOR ------------------------------------------------


def test_high_cves_above_threshold_raises_major(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, high_transitive_cves=15, high_transitive_cve_threshold=10)
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("high-severity" in rf.description.lower() for rf in major)


def test_high_cves_below_threshold_no_major_risk(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, high_transitive_cves=9, high_transitive_cve_threshold=10)
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert not any("high-severity transitive" in rf.description for rf in major)


# --- no SCA scan date → confidence cap -----------------------------------------------------------


def test_no_sca_scan_date_caps_confidence(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, sca_scan_date=None)).assess()
    assert result.confidence <= 0.65


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.DEPENDENCY_RISK


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_clean_when_no_critical_signals() -> None:
    data = DependencyRiskInput(
        known_malicious_packages=0,
        critical_transitive_cves=0,
        supply_chain_violations=0,
        high_transitive_cves=3,
        high_transitive_cve_threshold=10,
    )
    assert DependencyRiskAssessor._classify(data) == "clean"


def test_classify_compromised_when_malicious_packages() -> None:
    data = DependencyRiskInput(known_malicious_packages=1)
    assert DependencyRiskAssessor._classify(data) == "compromised"


def test_classify_at_risk_when_violations() -> None:
    data = DependencyRiskInput(
        known_malicious_packages=0,
        critical_transitive_cves=0,
        supply_chain_violations=1,
    )
    assert DependencyRiskAssessor._classify(data) == "at_risk"
