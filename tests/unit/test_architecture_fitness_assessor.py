"""Tests for ArchitectureFitnessAssessor (ADR-0016 item 15, gate-only dimension).

Uses synthetic tmp_path stubs. Score = tests_passed / tests_run (0 if no tests).
Layering/banned-dependency violations are CRITICAL; coupling/test failures are MAJOR.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.architecture_fitness import ArchitectureFitnessAssessor
from rrr.models.architecture_fitness import ArchitectureFitnessInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import ArchitectureFitnessSourceReader, ToolRunner


def _assessor(path: Path) -> ArchitectureFitnessAssessor:
    return ArchitectureFitnessAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        ArchitectureFitnessSourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal architecture_fitness.json stub, merging caller fields over a baseline."""
    base: dict[str, object] = {
        "tool": "ArchUnit",
        "scan_date": "2026-07-08",
        "fitness_functions_defined": 24,
        "tests_run": 24,
        "tests_passed": 24,
        "tests_failed": 0,
        "coupling_violations": 0,
        "layering_violations": 0,
        "banned_dependency_violations": 0,
        "violations": [],
    }
    base.update(fields)
    p = tmp_path / "architecture_fitness.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (all tests pass, no violations) -----------------------------------------------


def test_clean_posture_score_is_one(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.ARCHITECTURE_FITNESS
    assert result.available is True
    # 24/24 = 1.0
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "compliant"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "architecture_fitness_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "architecture_fitness_score" in labels


# --- layering violations → CRITICAL, violated ----------------------------------------------------


def test_layering_violations_raise_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, layering_violations=2)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("layering" in rf.description.lower() for rf in critical)


def test_layering_violations_classification_is_violated(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, layering_violations=1)).assess()
    assert result.classification == "violated"


# --- banned dependency violations → CRITICAL, violated -------------------------------------------


def test_banned_dependency_violations_raise_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, banned_dependency_violations=1)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("banned" in rf.description.lower() for rf in critical)


def test_banned_dependency_violations_classification_is_violated(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, banned_dependency_violations=3)).assess()
    assert result.classification == "violated"


# --- coupling violations → MAJOR, at_risk --------------------------------------------------------


def test_coupling_violations_raise_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, coupling_violations=2)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("coupling" in rf.description.lower() for rf in major)


def test_coupling_violations_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, coupling_violations=1)).assess()
    assert result.classification == "at_risk"


# --- failing tests → MAJOR -----------------------------------------------------------------------


def test_failing_tests_raise_major(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, tests_run=24, tests_passed=20, tests_failed=4)
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("fail" in rf.description.lower() for rf in major)


def test_failing_tests_score_is_pass_rate(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, tests_run=24, tests_passed=18, tests_failed=6)
    ).assess()
    # 18/24 = 0.75
    assert abs(result.score - 0.75) < 0.001


# --- no tests run → score=0, confidence cap -------------------------------------------------------


def test_no_tests_run_score_is_zero(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, tests_run=0, tests_passed=0, tests_failed=0, fitness_functions_defined=24)
    ).assess()
    assert result.score == 0.0


def test_no_tests_run_caps_confidence(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, tests_run=0, tests_passed=0, tests_failed=0)
    ).assess()
    assert result.confidence <= 0.65


def test_no_fitness_functions_defined_caps_confidence(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, fitness_functions_defined=0)).assess()
    assert result.confidence <= 0.65


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.ARCHITECTURE_FITNESS


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_compliant_when_no_violations() -> None:
    data = ArchitectureFitnessInput(
        tests_run=10,
        tests_passed=10,
        tests_failed=0,
        layering_violations=0,
        banned_dependency_violations=0,
        coupling_violations=0,
    )
    assert ArchitectureFitnessAssessor._classify(data) == "compliant"


def test_classify_violated_when_layering_violations() -> None:
    data = ArchitectureFitnessInput(layering_violations=1)
    assert ArchitectureFitnessAssessor._classify(data) == "violated"


def test_classify_at_risk_when_coupling_violations() -> None:
    data = ArchitectureFitnessInput(
        layering_violations=0,
        banned_dependency_violations=0,
        coupling_violations=2,
    )
    assert ArchitectureFitnessAssessor._classify(data) == "at_risk"
