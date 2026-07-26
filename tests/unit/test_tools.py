"""Tests for the tool layer: BaseTool, ToolRunner, RKTBrainReader (FR-10, FR-11)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from rrr.errors import BrainReadError, ToolInvocationError, ToolTimeoutError
from rrr.tools import BaseTool, BrainReadResult, RKTBrainReader, ToolRunner

BRAIN_DIR = Path(__file__).resolve().parents[1] / "golden" / "g1_clean_release" / "inputs" / "brain"
VALUE_STREAM = "Retirement-Services"
RELEASE = "Launch 36 - Unified Onboarding"


class _Echo:
    name = "echo"

    def invoke(self, **params: Any) -> Any:
        return params.get("value", "ok")


class _Slow:
    name = "slow"

    def invoke(self, **params: Any) -> Any:
        time.sleep(0.5)
        return "done"


class _Boom:
    name = "boom"

    def invoke(self, **params: Any) -> Any:
        raise ValueError("kaboom")


def test_runner_records_successful_invocation() -> None:
    result = ToolRunner().run(_Echo(), value="hello")
    assert result.output == "hello"
    inv = result.invocation
    assert inv.name == "echo" and inv.success is True
    assert inv.params == {"value": "hello"}
    assert inv.duration_ms >= 0 and inv.error_reason is None


def test_runner_timeout_raises_and_records_failure() -> None:
    with pytest.raises(ToolTimeoutError) as exc:
        ToolRunner().run(_Slow(), timeout=0.05)
    inv = exc.value.invocation
    assert inv is not None and inv.success is False
    assert "timeout" in (inv.error_reason or "")


def test_runner_wraps_tool_exception_and_carries_invocation() -> None:
    with pytest.raises(ToolInvocationError) as exc:
        ToolRunner().run(_Boom())
    assert isinstance(exc.value.__cause__, ValueError)
    inv = exc.value.invocation
    assert inv is not None and inv.success is False and "kaboom" in (inv.error_reason or "")


def test_runner_truncates_output_summary_to_500() -> None:
    result = ToolRunner().run(_Echo(), value="x" * 1000)
    assert len(result.invocation.output_summary) == 500


def test_runner_coerces_non_scalar_params_for_record() -> None:
    result = ToolRunner().run(_Echo(), value=[1, 2, 3])
    assert result.invocation.params["value"] == "[1, 2, 3]"


def test_brain_reader_satisfies_protocol() -> None:
    assert isinstance(RKTBrainReader(BRAIN_DIR), BaseTool)


def test_brain_reader_selects_latest_snapshot_and_release() -> None:
    out = RKTBrainReader(BRAIN_DIR).invoke(value_stream=VALUE_STREAM, ir_name=RELEASE)
    assert isinstance(out, BrainReadResult)
    assert out.snapshot_date == "2026-05-28"  # latest of the two snapshots
    assert out.release.ir_name == RELEASE
    assert out.release.summary.closed == 230


def test_brain_reader_exposes_planned_sp_history_for_scope_creep() -> None:
    out = RKTBrainReader(BRAIN_DIR).invoke(value_stream=VALUE_STREAM, ir_name=RELEASE)
    dates = [p.date for p in out.planned_sp_history]
    assert dates == ["2026-05-21", "2026-05-28"]  # chronological, baseline first
    assert all(p.total == 240 for p in out.planned_sp_history)  # no creep in g1


def test_brain_reader_selects_specific_snapshot_by_date() -> None:
    out = RKTBrainReader(BRAIN_DIR).invoke(
        value_stream=VALUE_STREAM, snapshot="2026-05-21", ir_name=RELEASE
    )
    assert out.snapshot_date == "2026-05-21"
    assert out.release.summary.closed == 205


def test_brain_reader_missing_file_raises() -> None:
    with pytest.raises(BrainReadError, match="not found"):
        RKTBrainReader(BRAIN_DIR).invoke(value_stream="No-Such-Stream")


def test_brain_reader_unknown_release_raises() -> None:
    with pytest.raises(BrainReadError, match="no release matches"):
        RKTBrainReader(BRAIN_DIR).invoke(value_stream=VALUE_STREAM, ir_name="Launch 99 - Ghost")


def test_brain_reader_unknown_snapshot_raises() -> None:
    with pytest.raises(BrainReadError, match="not found"):
        RKTBrainReader(BRAIN_DIR).invoke(
            value_stream=VALUE_STREAM, snapshot="2099-01-01", ir_name=RELEASE
        )


def test_runner_executes_brain_reader_end_to_end() -> None:
    result = ToolRunner().run(RKTBrainReader(BRAIN_DIR), value_stream=VALUE_STREAM, ir_name=RELEASE)
    assert isinstance(result.output, BrainReadResult)
    assert result.invocation.name == "rkt_brain_reader" and result.invocation.success is True


def test_list_releases_returns_release_records() -> None:
    records = RKTBrainReader(BRAIN_DIR).list_releases(VALUE_STREAM)
    assert len(records) > 0
    # All records in the golden fixture are OSM-native (no programme prefix in names).
    assert all(hasattr(r, "ir_name") for r in records)
    assert any(r.ir_name == RELEASE for r in records)


def test_list_releases_programme_filter_osm() -> None:
    # Golden fixture releases have no programme prefix → all default to "OSM".
    records = RKTBrainReader(BRAIN_DIR).list_releases(VALUE_STREAM, programme="OSM")
    assert len(records) > 0
    assert all(r.programme == "OSM" for r in records)


def test_list_releases_programme_filter_no_match_returns_empty() -> None:
    # No AIMS releases in the golden fixture.
    records = RKTBrainReader(BRAIN_DIR).list_releases(VALUE_STREAM, programme="AIMS")
    assert records == []


def test_select_release_programme_filter_scopes_fuzzy_match() -> None:
    # "Launch 36" uniquely matches in OSM programme within this fixture.
    result = RKTBrainReader(BRAIN_DIR).read(
        value_stream=VALUE_STREAM, ir_name="Launch 36", programme="OSM"
    )
    assert result.release.ir_name == RELEASE


# ---------------------------------------------------------------------------
# list_toc_value_streams (ADR-0021)
# ---------------------------------------------------------------------------


def test_list_toc_value_streams_empty_for_golden_fixture() -> None:
    # Golden fixtures were created before ADR-0021 — no toc_value_stream tags.
    result = RKTBrainReader(BRAIN_DIR).list_toc_value_streams(VALUE_STREAM)
    assert result == []


def test_list_toc_value_streams_empty_on_missing_file(tmp_path: Path) -> None:
    result = RKTBrainReader(tmp_path).list_toc_value_streams("No-Such-Stream")
    assert result == []


def test_list_toc_value_streams_returns_sorted_unique_names(tmp_path: Path) -> None:
    import json

    brain = {
        "value_stream": "Test",
        "snapshots": [
            {
                "date": "2026-06-28",
                "releases": [
                    {
                        "ir_name": "A",
                        "toc_value_stream": "Education & Advice",
                        "programme": "OSM",
                        "sq_avg": 2.0,
                        "summary": {"total": 10, "closed": 8, "remaining": 2, "pct": 80},
                        "defects_open": {"total": 0, "by_severity": {}},
                        "pv_latest": {"planned": 10.0, "actual": 8.0},
                    },
                    {
                        "ir_name": "B",
                        "toc_value_stream": "Account Management",
                        "programme": "OSM",
                        "sq_avg": 2.5,
                        "summary": {"total": 10, "closed": 9, "remaining": 1, "pct": 90},
                        "defects_open": {"total": 0, "by_severity": {}},
                        "pv_latest": {"planned": 10.0, "actual": 9.0},
                    },
                    {
                        "ir_name": "C",
                        "toc_value_stream": "Education & Advice",
                        "programme": "OSM",
                        "sq_avg": 1.5,
                        "summary": {"total": 5, "closed": 4, "remaining": 1, "pct": 80},
                        "defects_open": {"total": 0, "by_severity": {}},
                        "pv_latest": {"planned": 5.0, "actual": 4.0},
                    },
                    {
                        "ir_name": "D",
                        "toc_value_stream": None,
                        "programme": "AIMS",
                        "sq_avg": 3.0,
                        "summary": {"total": 5, "closed": 5, "remaining": 0, "pct": 100},
                        "defects_open": {"total": 0, "by_severity": {}},
                        "pv_latest": {"planned": 5.0, "actual": 5.0},
                    },
                ],
            }
        ],
    }
    (tmp_path / "Test-history.json").write_text(json.dumps(brain), encoding="utf-8")
    result = RKTBrainReader(tmp_path).list_toc_value_streams("Test")
    # Sorted, unique; None entries excluded.
    assert result == ["Account Management", "Education & Advice"]
