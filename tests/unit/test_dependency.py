"""Tests for DependencyAssessor (FR-5) — real fixtures + blocking cases."""

from __future__ import annotations

from pathlib import Path

from rrr.assessors import DependencyAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import DependencySourceReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1_DEP = GOLDEN / "g1_clean_release" / "inputs" / "dependency.json"
G3_DEP = GOLDEN / "g3_borderline" / "inputs" / "dependency.json"


def _assessor(path: Path) -> DependencyAssessor:
    return DependencyAssessor(ToolRunner(), RuleBasedProvider(), DependencySourceReader(path=path))


def test_g1_all_dependencies_ready() -> None:
    result = _assessor(G1_DEP).assess()
    assert result.dimension is DimensionName.DEPENDENCY and result.available is True
    assert result.score == 1.0  # matches g1 ideal.json
    assert result.classification == "ready"
    assert result.confidence == 1.0
    assert result.risk_factors == []


def test_g3_at_risk_dependency() -> None:
    result = _assessor(G3_DEP).assess()
    assert result.score == 0.75  # 3 of 4 ready
    assert result.classification == "at_risk"
    assert any(r.severity is RiskSeverity.MAJOR for r in result.risk_factors)


def test_failed_integration_is_critical_blocking(tmp_path: Path) -> None:
    src = tmp_path / "dependency.json"
    src.write_text(
        '{"dependencies": ['
        '{"name": "Payments", "completion": "complete", "integration": "failed"},'
        '{"name": "Notif", "completion": "complete", "integration": "passed"}]}',
        encoding="utf-8",
    )
    result = _assessor(src).assess()
    assert result.score == 0.5 and result.classification == "not_ready"
    crit = [r for r in result.risk_factors if r.severity is RiskSeverity.CRITICAL]
    assert len(crit) == 1 and "failed" in crit[0].description


def test_not_started_is_blocking(tmp_path: Path) -> None:
    src = tmp_path / "dependency.json"
    src.write_text(
        '{"dependencies": [{"name": "Ledger", "completion": "not_started", '
        '"integration": "not_validated"}]}',
        encoding="utf-8",
    )
    result = _assessor(src).assess()
    assert result.score == 0.0 and result.classification == "not_ready"
    assert any("not started" in r.description for r in result.risk_factors)
