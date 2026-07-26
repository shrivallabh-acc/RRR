"""Tests for AssessmentStore (FR-14), trend computation (FR-9),
run_and_record, WAL mode (T-03), and schema migration (T-07).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rrr.config import ConfigLoader
from rrr.memory import AbstractAssessmentStore, AssessmentStore
from rrr.memory.store import _SCHEMA_VERSION, SQLiteAssessmentStore
from rrr.models.assessment import AssessmentOutputModel, AuditTrail
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, TrendDirection, Verdict
from rrr.orchestration import compute_trends
from rrr.pipeline import run_and_record

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
VS = "Retirement-Services"


def _output(release: str, score: int, *, scope: float = 0.9) -> AssessmentOutputModel:
    return AssessmentOutputModel(
        release=release,
        value_stream=VS,
        verdict=Verdict.GO,
        score=score,
        dimensions=[
            DimensionResult(dimension=DimensionName.SCOPE, score=scope, confidence=1.0),
        ],
        audit_trail=AuditTrail(provider="RuleBasedProvider"),
    )


def _overrides(sample: str, tmp_path: Path) -> dict:
    inp = GOLDEN / sample / "inputs"
    return {
        "sources": {
            "brain": {"dir": str(inp / "brain"), "value_stream": VS},
            "environment": {"type": "file", "path": str(inp / "environment.json")},
            "dependency": {"type": "file", "path": str(inp / "dependency.json")},
        },
        "memory": {"sqlite_path": str(tmp_path / "rrr.sqlite")},
    }


# --- store ------------------------------------------------------------------------------------


def test_store_save_and_latest(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    assert store.latest_for("R1", VS) is None
    store.save(_output("R1", 80))
    store.save(_output("R1", 90))
    latest = store.latest_for("R1", VS)
    assert latest is not None and latest.score == 90  # most recent wins
    store.close()


def test_store_creates_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "rrr.sqlite"
    store = AssessmentStore(nested)
    store.save(_output("R", 50))
    assert nested.exists()
    store.close()


def test_store_history_newest_first(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    for s in (10, 20, 30):
        store.save(_output("R", s))
    hist = store.history("R", VS, limit=2)
    assert [h.score for h in hist] == [30, 20]
    store.close()


# --- trends -----------------------------------------------------------------------------------


def test_compute_trends_none_previous_is_empty() -> None:
    cfg = ConfigLoader.load()
    assert compute_trends(_output("R", 90), None, cfg.trend) == []


def test_compute_trends_directions() -> None:
    cfg = ConfigLoader.load()
    previous = _output("R", 80, scope=0.80)
    improving = compute_trends(_output("R", 90, scope=0.90), previous, cfg.trend)
    assert improving[0].direction is TrendDirection.IMPROVING and improving[0].delta == 0.1
    degrading = compute_trends(_output("R", 70, scope=0.70), previous, cfg.trend)
    assert degrading[0].direction is TrendDirection.DEGRADING
    stable = compute_trends(_output("R", 81, scope=0.81), previous, cfg.trend)
    assert stable[0].direction is TrendDirection.STABLE  # delta 0.01 within +/-0.05


# --- run_and_record (persist + trend) ---------------------------------------------------------


def test_run_and_record_persists_and_trends(tmp_path: Path) -> None:
    cfg = ConfigLoader.load(overrides=_overrides("g1_clean_release", tmp_path))
    release = "Launch 36 - Unified Onboarding"

    first = run_and_record(cfg, release=release)
    assert first.verdict is Verdict.GO and first.trend_data == []  # nothing to compare yet

    second = run_and_record(cfg, release=release)
    assert second.trend_data  # now has a prior assessment to trend against
    assert all(t.direction is TrendDirection.STABLE for t in second.trend_data)  # identical inputs

    store = AssessmentStore(cfg.memory.sqlite_path)
    assert len(store.history(release, VS, limit=10)) == 2
    store.close()


# --- all_recent (ADR-0020 dashboard history panel) -------------------------------------------


def test_all_recent_empty_store_returns_empty(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    assert store.all_recent() == []
    store.close()


def test_all_recent_returns_records_newest_first(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    for s in (10, 20, 30):
        store.save(_output("R", s))
    records = store.all_recent()
    assert [r.score for r in records] == [30, 20, 10]
    store.close()


def test_all_recent_filtered_by_value_stream(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    store.save(_output("R1", 80))  # VS = "Retirement-Services"
    other = AssessmentOutputModel(
        release="R2",
        value_stream="Other-Stream",
        verdict=Verdict.GO,
        score=50,
        audit_trail=AuditTrail(provider="RuleBasedProvider"),
    )
    store.save(other)
    in_stream = store.all_recent(value_stream=VS)
    assert len(in_stream) == 1 and in_stream[0].release == "R1"
    store.close()


def test_all_recent_respects_limit(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    for i in range(10):
        store.save(_output(f"R{i}", i * 10))
    records = store.all_recent(limit=3)
    assert len(records) == 3
    store.close()


def test_all_recent_no_value_stream_returns_all_streams(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    store.save(_output("R1", 80))
    other = AssessmentOutputModel(
        release="R2",
        value_stream="Other-Stream",
        verdict=Verdict.GO,
        score=50,
        audit_trail=AuditTrail(provider="RuleBasedProvider"),
    )
    store.save(other)
    all_records = store.all_recent()
    assert len(all_records) == 2
    store.close()


# --- assessed_releases (ADR-0020 Trends panel) -----------------------------------------------


def test_assessed_releases_empty_store(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    assert store.assessed_releases() == []
    store.close()


def test_assessed_releases_returns_distinct_names(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    for _ in range(3):
        store.save(_output("R1", 80))
    store.save(_output("R2", 70))
    releases = store.assessed_releases()
    # Distinct names only, alphabetically.
    assert releases == ["R1", "R2"]
    store.close()


def test_assessed_releases_filtered_by_value_stream(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    store.save(_output("R1", 80))  # VS = "Retirement-Services"
    other = AssessmentOutputModel(
        release="R2",
        value_stream="Other-Stream",
        verdict=Verdict.GO,
        score=50,
        audit_trail=AuditTrail(provider="RuleBasedProvider"),
    )
    store.save(other)
    in_stream = store.assessed_releases(value_stream=VS)
    assert in_stream == ["R1"]
    all_streams = store.assessed_releases()
    assert sorted(all_streams) == ["R1", "R2"]
    store.close()


def test_assessed_releases_alphabetical_order(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    # Insert in reverse alphabetical order — result must still be sorted.
    for name in ("Zebra Release", "Alpha Release", "Middle Release"):
        store.save(_output(name, 80))
    releases = store.assessed_releases()
    assert releases == ["Alpha Release", "Middle Release", "Zebra Release"]
    store.close()


# --- Chroma RAG (FR-24, ADR-0007) ------------------------------------------------------------


def test_chroma_similar_to_returns_empty_when_disabled(tmp_path: Path) -> None:
    """Without chroma_path the method returns [] rather than raising."""
    store = AssessmentStore(tmp_path / "db.sqlite")
    result = store.similar_to(_output("R", 80))
    assert result == []
    store.close()


def test_chroma_save_and_similar_to_in_memory(tmp_path: Path) -> None:
    """With an in-memory Chroma client, saved assessments are returned by similar_to."""
    store = AssessmentStore(tmp_path / "db.sqlite", chroma_path=":memory:")
    store.save(_output("R1", 90, scope=0.90))
    store.save(_output("R2", 85, scope=0.85))
    store.save(_output("R3", 30, scope=0.30))

    similar = store.similar_to(_output("R_query", 88, scope=0.88), k=2)
    # Verify the round-trip: k=2 returns exactly 2 results, each a valid assessment.
    assert len(similar) == 2
    all_saved_scores = {90, 85, 30}
    for s in similar:
        assert s.score in all_saved_scores
    store.close()


def test_chroma_similar_to_k_limits_results(tmp_path: Path) -> None:
    """k=1 returns exactly one result."""
    store = AssessmentStore(tmp_path / "db.sqlite", chroma_path=":memory:")
    for i in range(5):
        store.save(_output(f"R{i}", 80 + i, scope=0.80 + i * 0.01))
    similar = store.similar_to(_output("Q", 82, scope=0.82), k=1)
    assert len(similar) == 1
    store.close()


def test_chroma_similar_to_returns_empty_when_collection_empty(tmp_path: Path) -> None:
    """An empty collection returns [] without error."""
    store = AssessmentStore(tmp_path / "db.sqlite", chroma_path=":memory:")
    result = store.similar_to(_output("R", 80))
    assert result == []
    store.close()


# --- AbstractAssessmentStore interface contract (M5 hosted persistence) ----------------------


def test_sqlite_store_satisfies_abstract_interface(tmp_path: Path) -> None:
    store = SQLiteAssessmentStore(tmp_path / "db.sqlite")
    assert isinstance(store, AbstractAssessmentStore)
    store.close()


def test_assessment_store_alias_is_sqlite_store() -> None:
    assert AssessmentStore is SQLiteAssessmentStore


# --- WAL mode (T-03) --------------------------------------------------------------------------


def test_store_uses_wal_journal_mode(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal", f"Expected WAL mode, got {mode!r}"
    store.close()


# --- Schema migration guard (T-07) ------------------------------------------------------------


def test_migration_stamps_user_version_on_fresh_database(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "db.sqlite")
    version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == _SCHEMA_VERSION
    store.close()


def test_migration_is_idempotent_on_second_open(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = AssessmentStore(db)
    store.save(_output("R", 80))
    store.close()
    # Second open must not corrupt existing data or change the version.
    store2 = AssessmentStore(db)
    version = store2._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == _SCHEMA_VERSION
    assert store2.latest_for("R", VS) is not None
    store2.close()


def test_migration_upgrades_unversioned_database(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    # Simulate a pre-versioning database: create it manually with user_version=0.
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS assessments "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, release TEXT NOT NULL, "
        "value_stream TEXT NOT NULL, verdict TEXT NOT NULL, score INTEGER NOT NULL, "
        "generated_at TEXT NOT NULL, document TEXT NOT NULL);"
    )
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    # Opening via AssessmentStore must migrate it to the current schema version.
    store = AssessmentStore(db)
    version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == _SCHEMA_VERSION
    store.close()
