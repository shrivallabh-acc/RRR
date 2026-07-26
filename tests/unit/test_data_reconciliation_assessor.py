"""Tests for DataReconciliationAssessor (ADR-0016 item 11, gate-only dimension).

Uses synthetic tmp_path stubs. The gate is a no-op when migration_applicable=False.
When a migration is in scope, discrepancies are CRITICAL and missing approval is MAJOR.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.data_reconciliation import DataReconciliationAssessor
from rrr.models.data_reconciliation import DataReconciliationInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import DataReconciliationSourceReader, ToolRunner


def _assessor(path: Path) -> DataReconciliationAssessor:
    return DataReconciliationAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        DataReconciliationSourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal data_reconciliation.json stub, merging caller fields over a baseline."""
    base: dict[str, object] = {
        "migration_applicable": False,
        "reconciliation_run": False,
        "discrepancy_count": 0,
        "discrepancy_pct": 0.0,
        "reconciliation_approved": None,
    }
    base.update(fields)
    p = tmp_path / "data_reconciliation.json"
    p.write_text(json.dumps(base))
    return p


# --- migration not applicable (no-op) ------------------------------------------------------------


def test_not_applicable_score_is_one_and_no_risks(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, migration_applicable=False)).assess()
    assert result.dimension is DimensionName.DATA_RECONCILIATION
    assert result.available is True
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "not_applicable"
    assert not result.risk_factors


def test_not_applicable_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, migration_applicable=False)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "data_reconciliation_source"
    assert result.tool_invocations[0].success is True


# --- migration applicable, clean pass ------------------------------------------------------------


def test_clean_migration_score_is_one(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            migration_applicable=True,
            reconciliation_run=True,
            discrepancy_count=0,
            reconciliation_approved=True,
        )
    ).assess()
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "reconciled"
    assert not result.risk_factors


# --- reconciliation not run → CRITICAL -----------------------------------------------------------


def test_reconciliation_not_run_raises_critical(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, migration_applicable=True, reconciliation_run=False)
    ).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("reconciliation" in rf.description.lower() for rf in critical)


def test_reconciliation_not_run_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, migration_applicable=True, reconciliation_run=False)
    ).assess()
    assert result.classification == "at_risk"
    assert result.score == 0.0


# --- discrepancies found → CRITICAL --------------------------------------------------------------


def test_discrepancies_found_raises_critical(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            migration_applicable=True,
            reconciliation_run=True,
            discrepancy_count=5,
            discrepancy_pct=0.5,
        )
    ).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("reconcil" in rf.description.lower() or "discrepanc" in rf.description.lower()
               for rf in critical)


def test_discrepancies_found_classification_is_discrepancy(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            migration_applicable=True,
            reconciliation_run=True,
            discrepancy_count=3,
            discrepancy_pct=0.3,
        )
    ).assess()
    assert result.classification == "discrepancy"
    assert result.score == 0.0


# --- approval explicitly rejected → MAJOR --------------------------------------------------------


def test_approval_rejected_raises_major(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            migration_applicable=True,
            reconciliation_run=True,
            discrepancy_count=0,
            reconciliation_approved=False,
        )
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("approved" in rf.description.lower() or "owner" in rf.description.lower()
               for rf in major)


def test_approval_rejected_reduces_score(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            migration_applicable=True,
            reconciliation_run=True,
            discrepancy_count=0,
            reconciliation_approved=False,
        )
    ).assess()
    # reconciliation_run=True, no discrepancies → score=1.0; approved=False → ×0.5 = 0.5
    assert abs(result.score - 0.5) < 0.001


# --- approval pending → partial score, no risk ---------------------------------------------------


def test_approval_pending_reduces_score_without_risk(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            migration_applicable=True,
            reconciliation_run=True,
            discrepancy_count=0,
            reconciliation_approved=None,
        )
    ).assess()
    # score=1.0 × 0.75 = 0.75; no MAJOR raised for pending
    assert abs(result.score - 0.75) < 0.001
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert not major


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.DATA_RECONCILIATION


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_not_applicable_when_no_migration() -> None:
    data = DataReconciliationInput(migration_applicable=False)
    assert DataReconciliationAssessor._classify(data) == "not_applicable"


def test_classify_reconciled_when_clean_and_approved() -> None:
    data = DataReconciliationInput(
        migration_applicable=True,
        reconciliation_run=True,
        discrepancy_count=0,
        reconciliation_approved=True,
    )
    assert DataReconciliationAssessor._classify(data) == "reconciled"


def test_classify_discrepancy_when_run_but_mismatch() -> None:
    data = DataReconciliationInput(
        migration_applicable=True,
        reconciliation_run=True,
        discrepancy_count=1,
    )
    assert DataReconciliationAssessor._classify(data) == "discrepancy"


def test_classify_at_risk_when_not_run() -> None:
    data = DataReconciliationInput(
        migration_applicable=True,
        reconciliation_run=False,
    )
    assert DataReconciliationAssessor._classify(data) == "at_risk"
