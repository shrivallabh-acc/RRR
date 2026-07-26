"""Tests for PerformanceAssessor (ADR-0016, gate-only dimension).

Uses synthetic tmp_path stubs because the performance dimension is opt-in and
the golden fixtures pre-date it. All scoring assertions derive from the documented
formula in the assessor module docstring.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.performance import PerformanceAssessor, _capacity_score, _latency_score
from rrr.config.schema import PerformanceAssessorConfig
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import PerformanceSourceReader, ToolRunner

_DEFAULT_CONFIG = PerformanceAssessorConfig(
    low_capacity_threshold_pct=20.0,
    slo_critical_multiplier=2.0,
)


def _assessor(path: Path, cfg: PerformanceAssessorConfig = _DEFAULT_CONFIG) -> PerformanceAssessor:
    return PerformanceAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        PerformanceSourceReader(path=str(path)),
        cfg,
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal performance.json stub, merging caller fields over a clean baseline."""
    base = {
        "performance_test_status": "passed",
        "p99_latency_ms": 180.0,
        "slo_p99_threshold_ms": 500.0,
        "capacity_headroom_pct": 45.0,
    }
    base.update(fields)
    p = tmp_path / "performance.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (no risks) -----------------------------------------------------------------


def test_clean_posture_score_near_one(tmp_path: Path) -> None:
    """Passed test, latency well within SLO, ample headroom → score close to 1.0."""
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.PERFORMANCE
    assert result.available is True
    # perf(1.0)×0.5 + latency(180/500 ratio→clamped 1.0)×0.3 + cap(45/40→clamped 1.0)×0.2
    assert result.score >= 0.99
    assert result.classification == "clear"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "performance_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "performance_score" in labels


# --- load test failed → CRITICAL --------------------------------------------------------------


def test_load_test_failed_raises_critical_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, performance_test_status="failed")).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.CRITICAL in severities


def test_load_test_failed_classification_is_failed(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, performance_test_status="failed")).assess()
    assert result.classification == "failed"


def test_load_test_failed_score_reflects_zero_perf(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, performance_test_status="failed")).assess()
    # perf_score=0.0; latency + capacity still contribute
    assert result.score < 0.6


# --- critical SLO breach (≥ 2× threshold) → CRITICAL -----------------------------------------


def test_latency_at_2x_slo_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, p99_latency_ms=1000.0, slo_p99_threshold_ms=500.0)).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.CRITICAL in severities


def test_latency_at_2x_slo_classification_is_failed(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, p99_latency_ms=1000.0, slo_p99_threshold_ms=500.0)).assess()
    assert result.classification == "failed"


def test_latency_above_critical_multiplier_config(tmp_path: Path) -> None:
    """Custom multiplier of 1.5× — 750 ms against 500 ms SLO should be CRITICAL."""
    cfg = PerformanceAssessorConfig(slo_critical_multiplier=1.5, low_capacity_threshold_pct=20.0)
    result = _assessor(
        _stub(tmp_path, p99_latency_ms=750.0, slo_p99_threshold_ms=500.0), cfg=cfg
    ).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.CRITICAL in severities


# --- latency SLO breach (< 2×) → MAJOR -------------------------------------------------------


def test_latency_breach_below_critical_raises_major(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, p99_latency_ms=750.0, slo_p99_threshold_ms=500.0)).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.MAJOR in severities
    assert RiskSeverity.CRITICAL not in severities


def test_latency_breach_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, p99_latency_ms=750.0, slo_p99_threshold_ms=500.0)).assess()
    assert result.classification == "at_risk"


# --- low capacity → MAJOR ---------------------------------------------------------------------


def test_low_capacity_raises_major_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, capacity_headroom_pct=10.0)).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.MAJOR in severities


def test_low_capacity_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, capacity_headroom_pct=10.0)).assess()
    assert result.classification == "at_risk"


def test_capacity_at_threshold_is_not_at_risk(tmp_path: Path) -> None:
    """Exactly at the threshold (20 %) should not trigger the MAJOR risk."""
    result = _assessor(_stub(tmp_path, capacity_headroom_pct=20.0)).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.MAJOR not in severities


# --- load test not run → MINOR / confidence cap -----------------------------------------------


def test_not_run_raises_minor_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, performance_test_status="not_run")).assess()
    severities = [rf.severity for rf in result.risk_factors]
    assert RiskSeverity.MINOR in severities


def test_not_run_applies_confidence_cap(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, performance_test_status="not_run")).assess()
    assert result.confidence <= 0.75


def test_not_run_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, performance_test_status="not_run")).assess()
    assert result.classification == "at_risk"


# --- missing file → unavailable ---------------------------------------------------------------


def test_missing_file_marks_dimension_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "no_file.json"
    result = _assessor(path).assess()
    assert result.available is False
    assert result.dimension is DimensionName.PERFORMANCE


# --- score formula helpers --------------------------------------------------------------------


def test_latency_score_within_slo_is_one() -> None:
    assert _latency_score(300.0, 500.0) == 1.0


def test_latency_score_at_2x_slo_is_zero() -> None:
    assert _latency_score(1000.0, 500.0) == 0.0


def test_latency_score_at_1_5x_slo_is_half() -> None:
    assert abs(_latency_score(750.0, 500.0) - 0.5) < 0.001


def test_latency_score_no_data_is_half() -> None:
    assert _latency_score(None, 500.0) == 0.5
    assert _latency_score(300.0, None) == 0.5


def test_capacity_score_full_headroom_is_one() -> None:
    assert _capacity_score(40.0) == 1.0
    assert _capacity_score(80.0) == 1.0


def test_capacity_score_zero_headroom_is_zero() -> None:
    assert _capacity_score(0.0) == 0.0


def test_capacity_score_no_data_is_half() -> None:
    assert _capacity_score(None) == 0.5
