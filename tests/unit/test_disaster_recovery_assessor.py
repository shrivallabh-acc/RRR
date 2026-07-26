"""Tests for DisasterRecoveryAssessor (ADR-0016 item 10, gate-only dimension).

Uses synthetic tmp_path stubs. Scoring assertions derive from the weighted formula:
0.3×plan + 0.3×test + 0.2×rto + 0.2×rpo, documented in the assessor module.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.disaster_recovery import DisasterRecoveryAssessor
from rrr.models.disaster_recovery import DisasterRecoveryInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import DisasterRecoverySourceReader, ToolRunner


def _assessor(path: Path) -> DisasterRecoveryAssessor:
    return DisasterRecoveryAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        DisasterRecoverySourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal disaster_recovery.json stub, merging caller fields over a clean baseline."""
    base: dict[str, object] = {
        "dr_plan_exists": True,
        "dr_last_tested_date": "2026-06-01",
        "rto_target_minutes": 240,
        "rto_tested_minutes": 185,
        "rpo_target_minutes": 60,
        "rpo_tested_minutes": 42,
        "failover_tested": True,
        "data_backup_verified": True,
        "dr_test_max_age_days": 180,
    }
    base.update(fields)
    p = tmp_path / "disaster_recovery.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (all targets met) -------------------------------------------------------------


def test_clean_posture_score_is_one(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.DISASTER_RECOVERY
    assert result.available is True
    # plan=1.0×0.3 + test=1.0×0.3 + rto=1.0×0.2 + rpo=1.0×0.2 = 1.0
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "ready"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "disaster_recovery_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "dr_score" in labels


# --- dr_plan_exists=False → CRITICAL -------------------------------------------------------------


def test_no_dr_plan_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, dr_plan_exists=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("dr plan" in rf.description.lower() or "disaster recovery" in rf.description.lower()
               for rf in critical)


def test_no_dr_plan_classification_is_not_ready(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, dr_plan_exists=False)).assess()
    assert result.classification == "not_ready"


# --- failover_tested=False → CRITICAL ------------------------------------------------------------


def test_failover_untested_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, failover_tested=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("failover" in rf.description.lower() for rf in critical)


def test_failover_untested_classification_is_not_ready(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, failover_tested=False)).assess()
    assert result.classification == "not_ready"


# --- RTO breach → CRITICAL -----------------------------------------------------------------------


def test_rto_breach_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, rto_tested_minutes=300, rto_target_minutes=240)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("rto" in rf.description.lower() for rf in critical)


def test_rto_breach_classification_is_not_ready(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, rto_tested_minutes=300, rto_target_minutes=240)).assess()
    assert result.classification == "not_ready"


# --- RPO breach → CRITICAL -----------------------------------------------------------------------


def test_rpo_breach_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, rpo_tested_minutes=120, rpo_target_minutes=60)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("rpo" in rf.description.lower() for rf in critical)


# --- data_backup_verified=False → MAJOR ----------------------------------------------------------


def test_backup_unverified_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, data_backup_verified=False)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("backup" in rf.description.lower() for rf in major)


def test_backup_unverified_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, data_backup_verified=False)).assess()
    assert result.classification == "at_risk"


# --- stale DR test → MAJOR -----------------------------------------------------------------------


def test_stale_dr_test_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, dr_last_tested_date="2025-01-01", dr_test_max_age_days=180)
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("stale" in rf.description.lower() or "days old" in rf.description.lower()
               for rf in major)


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.DISASTER_RECOVERY


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_ready_when_all_controls_pass() -> None:
    data = DisasterRecoveryInput(
        dr_plan_exists=True,
        failover_tested=True,
        data_backup_verified=True,
    )
    assert DisasterRecoveryAssessor._classify(data, 1.0, 1.0) == "ready"


def test_classify_not_ready_when_no_plan() -> None:
    data = DisasterRecoveryInput(dr_plan_exists=False, failover_tested=False)
    assert DisasterRecoveryAssessor._classify(data, 1.0, 1.0) == "not_ready"


def test_classify_at_risk_when_backup_unverified() -> None:
    data = DisasterRecoveryInput(
        dr_plan_exists=True,
        failover_tested=True,
        data_backup_verified=False,
    )
    assert DisasterRecoveryAssessor._classify(data, 1.0, 1.0) == "at_risk"
