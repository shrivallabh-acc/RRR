"""Tests for RRR UI data helpers (ADR-0020).

The rendering functions require a running NiceGUI server (browser context) and
are not tested here.  The data helper functions in ``rrr.ui.app`` are pure Python
and can be tested in isolation without NiceGUI installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rrr.config.schema import FileSource, ValueStreamConfig
from rrr.memory import AssessmentStore
from rrr.models.assessment import AssessmentOutputModel, AuditTrail
from rrr.models.brain import DefectSeverity, DefectsOpen, E2EPoint, PVPoint, ReleaseRecord, Summary
from rrr.models.enums import Verdict
from rrr.ui.app import (
    collect_status_all,
    e2e_pct,
    latest_for_release,
    list_datasets,
    list_programmes,
    load_collect_form_data,
    load_dependency,
    load_environment,
    load_security_data,
    scope_pct,
    score_history_data,
    sq_normalized,
    vs_category,
)

_VS = "Retirement-Services"

_OSM_VS_CFG = ValueStreamConfig(
    canonical="OSM",
    aliases=["OSM", "OS&M", "Offer Selection & Management"],
    related_programmes=["AIMS", "EIMS", "PIMS"],
)


def _stored_output(store: AssessmentStore, score: int, release: str = "R1") -> None:
    """Save a minimal assessment to store with the given score."""
    store.save(
        AssessmentOutputModel(
            release=release,
            value_stream=_VS,
            verdict=Verdict.GO,
            score=score,
            audit_trail=AuditTrail(provider="RuleBasedProvider"),
        )
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _release(
    *,
    total: int = 100,
    closed: int = 90,
    sq_avg: float = 2.4,
    e2e: E2EPoint | None = None,
    remaining: int | None = None,
) -> ReleaseRecord:
    """Build a minimal ReleaseRecord for testing data helpers.

    ``remaining`` defaults to ``max(0, total - closed)``; pass an explicit value
    to construct edge-case records (InputContract has no cross-field constraint
    between total, closed, and remaining).
    """
    rem = remaining if remaining is not None else max(0, total - closed)
    return ReleaseRecord(
        ir_name="Test Release",
        summary=Summary(total=total, closed=closed, remaining=rem, pct=90.0),
        defects_open=DefectsOpen(total=0, by_severity=DefectSeverity()),
        sq_avg=sq_avg,
        pv_latest=PVPoint(planned=float(total), actual=float(closed)),
        e2e_latest=e2e,
    )


# ---------------------------------------------------------------------------
# scope_pct
# ---------------------------------------------------------------------------


def test_scope_pct_normal() -> None:
    assert scope_pct(_release(total=100, closed=90)) == pytest.approx(0.90)


def test_scope_pct_zero_total_returns_zero() -> None:
    assert scope_pct(_release(total=0, closed=0)) == 0.0


def test_scope_pct_capped_at_one() -> None:
    # closed can exceed total in upstream data (no cross-field constraint on InputContract).
    # remaining=0 is required since NonNegativeInt won't accept a negative default.
    assert scope_pct(_release(total=10, closed=15, remaining=0)) == 1.0


def test_scope_pct_full_completion() -> None:
    assert scope_pct(_release(total=50, closed=50)) == pytest.approx(1.0)


def test_scope_pct_partial() -> None:
    assert scope_pct(_release(total=200, closed=100)) == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# e2e_pct
# ---------------------------------------------------------------------------


def test_e2e_pct_no_e2e_returns_none() -> None:
    assert e2e_pct(_release(e2e=None)) is None


def test_e2e_pct_zero_run_returns_none() -> None:
    assert e2e_pct(_release(e2e=E2EPoint(passed=0, failed=0, planned=10))) is None


def test_e2e_pct_normal() -> None:
    result = e2e_pct(_release(e2e=E2EPoint(passed=8, failed=2, planned=10)))
    assert result == pytest.approx(0.80)


def test_e2e_pct_perfect() -> None:
    result = e2e_pct(_release(e2e=E2EPoint(passed=10, failed=0, planned=10)))
    assert result == pytest.approx(1.0)


def test_e2e_pct_all_failed() -> None:
    result = e2e_pct(_release(e2e=E2EPoint(passed=0, failed=5, planned=5)))
    assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# sq_normalized
# ---------------------------------------------------------------------------


def test_sq_normalized_full_score() -> None:
    # SQ avg of 3.0 (max) should normalise to 1.0.
    assert sq_normalized(_release(sq_avg=3.0)) == pytest.approx(1.0)


def test_sq_normalized_half() -> None:
    assert sq_normalized(_release(sq_avg=1.5)) == pytest.approx(0.5)


def test_sq_normalized_zero() -> None:
    assert sq_normalized(_release(sq_avg=0.0)) == pytest.approx(0.0)


def test_sq_normalized_at_max() -> None:
    # sq_avg is Pydantic-constrained to le=3.0; max value maps to exactly 1.0.
    assert sq_normalized(_release(sq_avg=3.0)) == pytest.approx(1.0)


def test_sq_normalized_typical() -> None:
    # 2.4 / 3.0 = 0.80
    assert sq_normalized(_release(sq_avg=2.4)) == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# score_history_data
# ---------------------------------------------------------------------------


def test_score_history_data_empty_store(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    timestamps, scores = score_history_data(store, "R1", _VS)
    assert timestamps == [] and scores == []
    store.close()


def test_score_history_data_ordered_oldest_first(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    for s in (10, 20, 30):
        _stored_output(store, s)
    timestamps, scores = score_history_data(store, "R1", _VS)
    assert scores == [10, 20, 30]  # oldest → newest (reversed from history())
    assert len(timestamps) == 3
    store.close()


def test_score_history_data_respects_limit(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    for s in range(10):
        _stored_output(store, s * 10)
    _, scores = score_history_data(store, "R1", _VS, limit=4)
    assert len(scores) == 4
    store.close()


def test_score_history_data_timestamp_format(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    _stored_output(store, 80)
    timestamps, _ = score_history_data(store, "R1", _VS)
    # Expect "YYYY-MM-DD HH:MM" format — 16 chars.
    assert len(timestamps) == 1 and len(timestamps[0]) == 16
    store.close()


def test_score_history_data_isolates_by_release(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    _stored_output(store, 80, release="R1")
    _stored_output(store, 50, release="R2")
    _, scores_r1 = score_history_data(store, "R1", _VS)
    _, scores_r2 = score_history_data(store, "R2", _VS)
    assert scores_r1 == [80]
    assert scores_r2 == [50]
    store.close()


# ---------------------------------------------------------------------------
# vs_category
# ---------------------------------------------------------------------------


class _FakeConfig:
    """Minimal config stub that exposes only the value_stream attribute."""

    def __init__(self, vs_cfg: ValueStreamConfig | None) -> None:
        self.value_stream = vs_cfg


def _prog_release(
    programme: str,
    ir_name: str = "Test Release",
    dependency_for: str | None = None,
) -> ReleaseRecord:
    """Build a ReleaseRecord with a specific programme code for VS classification tests."""
    from rrr.models.brain import ReleaseRelationship

    rr = (
        ReleaseRelationship(dependency_for=dependency_for, enables_release="Target Release")
        if dependency_for
        else None
    )
    return ReleaseRecord(
        ir_name=ir_name,
        programme=programme,
        summary=Summary(total=10, closed=9, remaining=1, pct=90.0),
        defects_open=DefectsOpen(total=0, by_severity=DefectSeverity()),
        sq_avg=2.0,
        pv_latest=PVPoint(planned=10.0, actual=9.0),
        release_relationship=rr,
    )


def test_vs_category_no_registry_returns_other() -> None:
    r = _prog_release("OSM")
    assert vs_category(r, _FakeConfig(None)) == "other"  # type: ignore[arg-type]


def test_vs_category_direct_exact_alias_match() -> None:
    r = _prog_release("OSM")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "direct"  # type: ignore[arg-type]


def test_vs_category_direct_alias_variant() -> None:
    # "OS&M" is in the aliases list — programme field may use that form.
    r = _prog_release("OS&M")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "direct"  # type: ignore[arg-type]


def test_vs_category_dependency_via_dependency_for() -> None:
    # Non-OSM programme whose dependency_for mentions an OSM alias.
    r = _prog_release("DIST", dependency_for="OS&M")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "dependency"  # type: ignore[arg-type]


def test_vs_category_supporting_from_related_programme() -> None:
    r = _prog_release("AIMS")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "supporting"  # type: ignore[arg-type]


def test_vs_category_supporting_eims() -> None:
    r = _prog_release("EIMS")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "supporting"  # type: ignore[arg-type]


def test_vs_category_other_unrelated_programme() -> None:
    r = _prog_release("ME&Q")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "other"  # type: ignore[arg-type]


def test_vs_category_direct_beats_dependency() -> None:
    # OSM release that also has dependency_for set — direct takes priority.
    r = _prog_release("OSM", dependency_for="OS&M")
    assert vs_category(r, _FakeConfig(_OSM_VS_CFG)) == "direct"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# list_datasets (ADR-0022)
# ---------------------------------------------------------------------------


class _FakeBrainConfig:
    """Minimal config stub for list_datasets — only needs config.sources.brain.dir."""

    class _Brain:
        def __init__(self, dir_: str) -> None:
            self.dir = dir_

    class _Sources:
        def __init__(self, dir_: str) -> None:
            self.brain = _FakeBrainConfig._Brain(dir_)

    def __init__(self, dir_: str) -> None:
        self.sources = _FakeBrainConfig._Sources(dir_)


def test_list_datasets_empty_when_dir_missing(tmp_path: Path) -> None:
    cfg = _FakeBrainConfig(str(tmp_path / "no_such_dir"))
    assert list_datasets(cfg) == []  # type: ignore[arg-type]


def test_list_datasets_returns_sorted_labels(tmp_path: Path) -> None:
    (tmp_path / "ZZZ-history.json").write_text("{}")
    (tmp_path / "AAA-history.json").write_text("{}")
    (tmp_path / "OSM-history.json").write_text("{}")
    cfg = _FakeBrainConfig(str(tmp_path))
    assert list_datasets(cfg) == ["AAA", "OSM", "ZZZ"]  # type: ignore[arg-type]


def test_list_datasets_ignores_non_history_files(tmp_path: Path) -> None:
    (tmp_path / "OSM-history.json").write_text("{}")
    (tmp_path / "OSM.json").write_text("{}")
    (tmp_path / "README.md").write_text("ignore")
    cfg = _FakeBrainConfig(str(tmp_path))
    assert list_datasets(cfg) == ["OSM"]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# list_programmes (ADR-0022)
# ---------------------------------------------------------------------------


def test_list_programmes_empty_when_single_programme() -> None:
    releases = [_prog_release("OSM"), _prog_release("OSM", ir_name="R2")]
    assert list_programmes(releases) == []


def test_list_programmes_empty_when_no_releases() -> None:
    assert list_programmes([]) == []


def test_list_programmes_returns_sorted_codes() -> None:
    releases = [_prog_release("ME&Q"), _prog_release("AIMS"), _prog_release("OSM")]
    assert list_programmes(releases) == ["AIMS", "ME&Q", "OSM"]


def test_list_programmes_deduplicates_codes() -> None:
    releases = [_prog_release("OSM"), _prog_release("OSM", ir_name="R2"), _prog_release("AIMS")]
    result = list_programmes(releases)
    assert result == ["AIMS", "OSM"]
    assert result.count("OSM") == 1


# ---------------------------------------------------------------------------
# _FakeSourcesConfig — stub for load_environment / load_dependency / load_security_data
# ---------------------------------------------------------------------------


class _FakeSourcesConfig:
    """Minimal config stub for load_environment/load_dependency/load_security_data.

    Provides only ``config.sources.environment``, ``.dependency``, and ``.security``
    using real ``FileSource`` instances so the reader constructor receives a valid
    source object with a ``path`` attribute.
    """

    class _Sources:
        def __init__(
            self,
            env: FileSource | None = None,
            dep: FileSource | None = None,
            sec: FileSource | None = None,
        ) -> None:
            self.environment = env
            self.dependency = dep
            self.security = sec

    def __init__(
        self,
        env: FileSource | None = None,
        dep: FileSource | None = None,
        sec: FileSource | None = None,
    ) -> None:
        self.sources = _FakeSourcesConfig._Sources(env=env, dep=dep, sec=sec)


# ---------------------------------------------------------------------------
# load_environment
# ---------------------------------------------------------------------------


def test_load_environment_returns_none_on_missing_file(tmp_path: Path) -> None:
    cfg = _FakeSourcesConfig(env=FileSource(path=str(tmp_path / "no_env.json")))
    assert load_environment(cfg) is None  # type: ignore[arg-type]


def test_load_environment_returns_data_on_valid_file(tmp_path: Path) -> None:
    env_file = tmp_path / "env.json"
    env_file.write_text(
        '{"components": [{"name": "api", "provisioning": "provisioned", "stability": "stable"}]}',
        encoding="utf-8",
    )
    cfg = _FakeSourcesConfig(env=FileSource(path=str(env_file)))
    result = load_environment(cfg)  # type: ignore[arg-type]
    assert result is not None
    assert result.components[0].name == "api"


def test_load_environment_returns_none_on_invalid_json(tmp_path: Path) -> None:
    env_file = tmp_path / "env.json"
    env_file.write_text("not valid json", encoding="utf-8")
    cfg = _FakeSourcesConfig(env=FileSource(path=str(env_file)))
    assert load_environment(cfg) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# load_dependency
# ---------------------------------------------------------------------------


def test_load_dependency_returns_none_on_missing_file(tmp_path: Path) -> None:
    cfg = _FakeSourcesConfig(dep=FileSource(path=str(tmp_path / "no_dep.json")))
    assert load_dependency(cfg) is None  # type: ignore[arg-type]


def test_load_dependency_returns_data_on_valid_file(tmp_path: Path) -> None:
    dep_file = tmp_path / "dep.json"
    dep_file.write_text(
        '{"dependencies": [{"name": "upstream-api",'
        ' "completion": "complete", "integration": "passed"}]}',
        encoding="utf-8",
    )
    cfg = _FakeSourcesConfig(dep=FileSource(path=str(dep_file)))
    result = load_dependency(cfg)  # type: ignore[arg-type]
    assert result is not None
    assert result.dependencies[0].name == "upstream-api"


# ---------------------------------------------------------------------------
# load_security_data
# ---------------------------------------------------------------------------


def test_load_security_data_returns_none_when_not_configured() -> None:
    # sources.security is None (not configured) → must return None.
    cfg = _FakeSourcesConfig()  # no sec= → sources.security is None
    assert load_security_data(cfg) is None  # type: ignore[arg-type]


def test_load_security_data_returns_data_on_valid_file(tmp_path: Path) -> None:
    sec_file = tmp_path / "security.json"
    sec_file.write_text(
        '{"sast_status": "passed", "dast_status": "not_run",'
        ' "open_critical_cves": 0, "open_high_cves": 0}',
        encoding="utf-8",
    )
    cfg = _FakeSourcesConfig(sec=FileSource(path=str(sec_file)))
    result = load_security_data(cfg)  # type: ignore[arg-type]
    assert result is not None
    assert result.sast_status.value == "passed"


def test_load_security_data_returns_none_on_missing_file(tmp_path: Path) -> None:
    cfg = _FakeSourcesConfig(sec=FileSource(path=str(tmp_path / "no_sec.json")))
    assert load_security_data(cfg) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# latest_for_release
# ---------------------------------------------------------------------------


def test_latest_for_release_returns_none_when_empty(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    result = latest_for_release(store, "R1", _VS)
    assert result is None
    store.close()


def test_latest_for_release_returns_most_recent(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    # Save three records for the same release; history() returns newest-first.
    for s in (10, 50, 90):
        _stored_output(store, s)
    result = latest_for_release(store, "R1", _VS)
    # latest_for_release wraps history(limit=1) — newest record wins.
    assert result is not None
    assert result.score == 90
    store.close()


# ---------------------------------------------------------------------------
# collect_status_all (M7 Phase 2, ADR-0023)
# ---------------------------------------------------------------------------


def test_collect_status_all_empty_dir_all_missing(tmp_path: Path) -> None:
    from rrr.collectors.runner import CollectorStatus

    reports = collect_status_all(tmp_path)
    # All 14 registered dimensions must be accounted for and all MISSING.
    assert len(reports) == 14
    assert all(r.status is CollectorStatus.MISSING for r in reports)


def test_collect_status_all_fresh_file_detected(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from rrr.collectors.runner import CollectorStatus

    # Write a fresh operability.json with a current timestamp.
    (tmp_path / "operability.json").write_text(
        '{"captured_at": "' + datetime.now(UTC).isoformat() + '"}',
        encoding="utf-8",
    )
    reports = collect_status_all(tmp_path)
    operability = next(r for r in reports if r.dimension == "operability")
    assert operability.status is CollectorStatus.FRESH


def test_collect_status_all_stale_file_detected(tmp_path: Path) -> None:
    from rrr.collectors.runner import CollectorStatus

    # Write a file with a timestamp from 30 days ago — staleness_days default is 7.
    (tmp_path / "operability.json").write_text(
        '{"captured_at": "2020-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    reports = collect_status_all(tmp_path)
    operability = next(r for r in reports if r.dimension == "operability")
    assert operability.status is CollectorStatus.STALE


# ---------------------------------------------------------------------------
# load_collect_form_data (M7 Phase 2, ADR-0023)
# ---------------------------------------------------------------------------


def test_load_collect_form_data_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_collect_form_data(tmp_path, "operability") == {}


def test_load_collect_form_data_returns_parsed_json(tmp_path: Path) -> None:
    (tmp_path / "operability.json").write_text('{"key": "value"}', encoding="utf-8")
    assert load_collect_form_data(tmp_path, "operability") == {"key": "value"}


def test_load_collect_form_data_returns_empty_on_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "operability.json").write_text("not valid json", encoding="utf-8")
    assert load_collect_form_data(tmp_path, "operability") == {}
