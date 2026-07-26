"""Unit tests for K6Adapter — reads k6 summary JSON → PerformanceInput."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rrr.collectors.adapters.k6 import K6Adapter, K6AdapterError
from rrr.collectors.base import CollectorConfig
from rrr.collectors.registry import CollectorRegistry
from rrr.collectors.runner import CollectorRunner

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _summary(
    p99: float | None = 187.4,
    check_fails: int = 0,
    extra_metrics: dict | None = None,
) -> dict:
    """Build a minimal k6 summary-export dict."""
    duration_values: dict = {"avg": 120.0, "min": 90.0, "med": 110.0, "max": 450.0}
    if p99 is not None:
        duration_values["p(99)"] = p99
    metrics = {
        "http_req_duration": {"type": "trend", "contains": "time", "values": duration_values},
        "checks": {
            "type": "rate",
            "contains": "default",
            "values": {
                "rate": 1.0 if check_fails == 0 else 0.9,
                "passes": 100,
                "fails": check_fails,
            },
        },
    }
    if extra_metrics:
        metrics.update(extra_metrics)
    return {"metrics": metrics}


def _write_summary(tmp_path: Path, data: dict) -> Path:
    """Write a k6 summary dict to a temp file and return its path."""
    p = tmp_path / "k6-summary.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_k6_adapter_dimension_is_performance(tmp_path):
    adapter = K6Adapter(tmp_path / "irrelevant.json")
    assert adapter.dimension == "performance"


def test_k6_adapter_passed_when_no_check_failures(tmp_path):
    path = _write_summary(tmp_path, _summary(check_fails=0))
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert result["performance_test_status"] == "passed"


def test_k6_adapter_failed_when_checks_fail(tmp_path):
    path = _write_summary(tmp_path, _summary(check_fails=5))
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert result["performance_test_status"] == "failed"


def test_k6_adapter_maps_p99_latency(tmp_path):
    path = _write_summary(tmp_path, _summary(p99=312.7))
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert result["p99_latency_ms"] == pytest.approx(312.7)


def test_k6_adapter_no_p99_when_metric_absent(tmp_path):
    path = _write_summary(tmp_path, _summary(p99=None))
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert "p99_latency_ms" not in result


def test_k6_adapter_no_capacity_headroom_in_output(tmp_path):
    # K6 does not report capacity headroom — the field must be absent so the
    # InputContract default (None) applies rather than an incorrect value.
    path = _write_summary(tmp_path, _summary())
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert "capacity_headroom_pct" not in result


def test_k6_adapter_raises_when_file_missing(tmp_path):
    adapter = K6Adapter(tmp_path / "nonexistent.json")
    with pytest.raises(K6AdapterError, match="not found"):
        adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))


def test_k6_adapter_raises_on_invalid_json(tmp_path):
    bad_file = tmp_path / "k6-summary.json"
    bad_file.write_text("not-json{{{", encoding="utf-8")
    adapter = K6Adapter(bad_file)
    with pytest.raises(K6AdapterError, match="Failed to read"):
        adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))


def test_k6_adapter_handles_empty_metrics(tmp_path):
    # No metrics block → defaults: passed, no p99.
    path = tmp_path / "k6-summary.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert result["performance_test_status"] == "passed"
    assert "p99_latency_ms" not in result


def test_k6_adapter_handles_missing_checks_block(tmp_path):
    # checks key absent → no check failures → "passed".
    data = {"metrics": {"http_req_duration": {"values": {"p(99)": 200.0}}}}
    path = _write_summary(tmp_path, data)
    adapter = K6Adapter(path)
    result = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    assert result["performance_test_status"] == "passed"


def test_k6_adapter_result_validates_against_performance_input(tmp_path):
    from rrr.models.performance import PerformanceInput

    path = _write_summary(tmp_path, _summary(p99=250.0, check_fails=0))
    adapter = K6Adapter(path)
    raw = adapter.collect(CollectorConfig(release="R1", data_dir=tmp_path))
    # Should not raise.
    model = PerformanceInput.model_validate(raw)
    assert model.p99_latency_ms == pytest.approx(250.0)
    assert model.performance_test_status.value == "passed"


def test_k6_adapter_writes_via_runner(tmp_path):
    registry = CollectorRegistry()
    runner = CollectorRunner()
    path = _write_summary(tmp_path, _summary(p99=100.0))
    adapter = K6Adapter(path)
    config = CollectorConfig(release="sprint-42", data_dir=tmp_path)

    result = runner.run("performance", adapter, config, registry.model_for("performance"))

    written = tmp_path / "performance.json"
    assert written.exists()
    data = json.loads(written.read_text())
    assert data["performance_test_status"] == "passed"
    assert data["p99_latency_ms"] == pytest.approx(100.0)
    assert result.collected_at != ""
