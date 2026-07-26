"""Tests for FailureModeAssessor (ADR-0016 item 12, gate-only dimension).

Uses synthetic tmp_path stubs. Scoring: 0.25×doc + 0.25×circuit + 0.25×chaos_rate
+ 0.25×degradation, as documented in the assessor module docstring.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.failure_mode import FailureModeAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.failure_mode import FailureModeInput
from rrr.providers import RuleBasedProvider
from rrr.tools import FailureModeSourceReader, ToolRunner


def _assessor(path: Path) -> FailureModeAssessor:
    return FailureModeAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        FailureModeSourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal failure_mode.json stub, merging caller fields over a clean baseline."""
    base: dict[str, object] = {
        "failure_modes_documented": True,
        "critical_paths_covered_pct": 95.0,
        "circuit_breakers_configured": True,
        "timeout_policies_defined": True,
        "chaos_tests_run": True,
        "chaos_pass_rate_pct": 92.0,
        "chaos_pass_threshold_pct": 80.0,
        "graceful_degradation_tested": True,
        "fmea_complete": True,
    }
    base.update(fields)
    p = tmp_path / "failure_mode.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (all resilience controls in place) --------------------------------------------


def test_clean_posture_score_near_one(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.FAILURE_MODE
    assert result.available is True
    # 0.25×1 + 0.25×1 + 0.25×0.92 + 0.25×1 = 0.98
    assert abs(result.score - 0.98) < 0.001
    assert result.classification == "resilient"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "failure_mode_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "failure_mode_score" in labels


# --- failure_modes_documented=False → CRITICAL ---------------------------------------------------


def test_undocumented_failure_modes_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, failure_modes_documented=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("failure mode" in rf.description.lower() for rf in critical)


def test_undocumented_failure_modes_classification_is_not_resilient(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, failure_modes_documented=False)).assess()
    assert result.classification == "not_resilient"


# --- circuit_breakers_configured=False → CRITICAL ------------------------------------------------


def test_missing_circuit_breakers_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, circuit_breakers_configured=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("circuit breaker" in rf.description.lower() for rf in critical)


def test_missing_circuit_breakers_classification_is_not_resilient(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, circuit_breakers_configured=False)).assess()
    assert result.classification == "not_resilient"


# --- chaos_tests_run=False → MAJOR ---------------------------------------------------------------


def test_chaos_tests_not_run_raises_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, chaos_tests_run=False)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("chaos" in rf.description.lower() for rf in major)


def test_chaos_tests_not_run_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, chaos_tests_run=False)).assess()
    assert result.classification == "at_risk"


# --- chaos pass rate below threshold → MAJOR -----------------------------------------------------


def test_low_chaos_pass_rate_raises_major(tmp_path: Path) -> None:
    result = _assessor(
        _stub(tmp_path, chaos_tests_run=True, chaos_pass_rate_pct=60.0,
              chaos_pass_threshold_pct=80.0)
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("chaos" in rf.description.lower() and "pass rate" in rf.description.lower()
               for rf in major)


# --- graceful_degradation_tested=False → MAJOR ---------------------------------------------------


def test_degradation_untested_raises_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, graceful_degradation_tested=False)).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("graceful degradation" in rf.description.lower() for rf in major)


def test_degradation_untested_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, graceful_degradation_tested=False)).assess()
    assert result.classification == "at_risk"


# --- score formula direct check ------------------------------------------------------------------


def test_score_formula_with_no_chaos(tmp_path: Path) -> None:
    # chaos_tests_run=False → chaos_score=0.0; score = 0.25+0.25+0+0.25 = 0.75
    result = _assessor(_stub(tmp_path, chaos_tests_run=False)).assess()
    assert abs(result.score - 0.75) < 0.001


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.FAILURE_MODE


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_resilient_when_all_controls_pass() -> None:
    data = FailureModeInput(
        failure_modes_documented=True,
        circuit_breakers_configured=True,
        chaos_tests_run=True,
        chaos_pass_rate_pct=90.0,
        chaos_pass_threshold_pct=80.0,
        graceful_degradation_tested=True,
    )
    assert FailureModeAssessor._classify(data) == "resilient"


def test_classify_not_resilient_when_circuit_breakers_absent() -> None:
    data = FailureModeInput(
        failure_modes_documented=True,
        circuit_breakers_configured=False,
        chaos_tests_run=True,
        chaos_pass_rate_pct=90.0,
    )
    assert FailureModeAssessor._classify(data) == "not_resilient"


def test_classify_at_risk_when_chaos_not_run() -> None:
    data = FailureModeInput(
        failure_modes_documented=True,
        circuit_breakers_configured=True,
        chaos_tests_run=False,
        graceful_degradation_tested=True,
    )
    assert FailureModeAssessor._classify(data) == "at_risk"
