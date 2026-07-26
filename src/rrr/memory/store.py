"""Assessment store — abstract interface + SQLite/Chroma local impl (FR-14, ADR-0003/0007).

``AbstractAssessmentStore`` defines the contract every storage backend must satisfy.
``SQLiteAssessmentStore`` (aliased as ``AssessmentStore``) is the canonical local-first
impl: zero-config, file-based SQLite with optional Chroma RAG. The abstract base class
keeps the pipeline decoupled from the concrete backend so future backends can be added
by subclassing without touching orchestration code.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from rrr.errors import PersistenceError
from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import DimensionName

logger = logging.getLogger(__name__)

# Ordered dimension slots for the embedding vector.
_DIM_ORDER = (
    DimensionName.SCOPE,
    DimensionName.ESTIMATION,
    DimensionName.ENVIRONMENT,
    DimensionName.TEST_READINESS,
    DimensionName.DEPENDENCY,
)

# Sentinel value: pass chroma_path=":memory:" in tests for an ephemeral client.
_IN_MEMORY = ":memory:"


def _make_embedding(output: AssessmentOutputModel) -> list[float]:
    """Build a 6-float embedding from dimension scores + overall score (FR-24).

    The vector is [scope, estimation, environment, test_readiness, dependency, score/100].
    Unavailable dimensions contribute 0.0 so the vector length is always fixed.
    This intentionally simple representation captures "release risk profile" without
    requiring an external embedding model — no LLM call, no cloud dependency.
    """
    scores = {d.dimension: d.score for d in output.dimensions}
    return [scores.get(dim, 0.0) for dim in _DIM_ORDER] + [output.score / 100.0]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    release       TEXT NOT NULL,
    value_stream  TEXT NOT NULL,
    verdict       TEXT NOT NULL,
    score         INTEGER NOT NULL,
    generated_at  TEXT NOT NULL,
    document      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessments_release
    ON assessments (release, value_stream, generated_at);
"""

# Schema version — bump whenever the SQLite schema changes (new columns, indexes, etc.).
# Write one migration list per increment in _MIGRATIONS below.
_SCHEMA_VERSION = 1

# SQL statements run for each version step.  Index 0 migrates version 0 → 1, etc.
# Each inner list may contain zero or more SQL strings; they run in order, then
# PRAGMA user_version is updated atomically before the next step begins.
_MIGRATIONS: list[list[str]] = [
    # 0 → 1: WAL mode + user_version tracking established; no column changes yet.
    # All M6 tier/sub-score fields live inside the JSON document column and are
    # Optional in AssessmentOutputModel, so they remain backward-compatible.
    [],
]

# Chroma collection name — all assessments share one collection (each doc is one assessment).
_CHROMA_COLLECTION = "assessments"


def _migrate(conn: sqlite3.Connection) -> None:
    """Run any pending schema migrations and stamp PRAGMA user_version.

    Reads the current user_version (0 on a fresh or pre-versioned database),
    then applies each migration list in _MIGRATIONS in order until the schema
    reaches _SCHEMA_VERSION.  Each migration is a list of SQL statements;
    user_version is bumped after every step so a crash mid-migration is safe
    — the next open will resume from the last committed version.
    """
    current: int = conn.execute("PRAGMA user_version").fetchone()[0]
    for version in range(current + 1, _SCHEMA_VERSION + 1):
        for sql in _MIGRATIONS[version - 1]:
            conn.execute(sql)
        # PRAGMA user_version persists in the database header; commit seals the step.
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()


class AbstractAssessmentStore(ABC):
    """Contract every assessment-store backend must satisfy (M5 hosted persistence)."""

    @abstractmethod
    def save(self, output: AssessmentOutputModel) -> int:
        """Persist an assessment and return an opaque record identifier."""

    @abstractmethod
    def latest_for(self, release: str, value_stream: str) -> AssessmentOutputModel | None:
        """Return the most recent prior assessment for a release, or None."""

    @abstractmethod
    def history(
        self, release: str, value_stream: str, *, limit: int = 10
    ) -> list[AssessmentOutputModel]:
        """Return up to ``limit`` assessments for a release, newest first."""

    @abstractmethod
    def similar_to(
        self, output: AssessmentOutputModel, *, k: int = 3
    ) -> list[AssessmentOutputModel]:
        """Return the k most similar past assessments by score embedding (FR-24, ADR-0007).

        Backends that do not support vector similarity MUST return an empty list,
        not raise — callers treat this as a best-effort enrichment, never a hard dependency.
        """

    @abstractmethod
    def all_recent(
        self, value_stream: str | None = None, *, limit: int = 50
    ) -> list[AssessmentOutputModel]:
        """Return up to ``limit`` most recent assessments across all releases, newest first."""

    @abstractmethod
    def assessed_releases(self, value_stream: str | None = None) -> list[str]:
        """Return distinct release names that have at least one assessment, alphabetically."""

    @abstractmethod
    def close(self) -> None:
        """Release any held resources (connections, file handles, etc.)."""


class SQLiteAssessmentStore(AbstractAssessmentStore):
    """SQLite store for assessment records, with optional Chroma vector index (ADR-0003/0007)."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        retry_attempts: int = 3,
        retry_interval: float = 5.0,
        chroma_path: str | None = None,
    ) -> None:
        """Open (or create) the SQLite database and, if ``chroma_path`` is given, the Chroma index.

        Args:
            db_path: Path to the SQLite database file.
            retry_attempts: How many times to retry a locked-database write.
            retry_interval: Seconds to wait between retry attempts.
            chroma_path: Optional path for Chroma persistence. Pass ``":memory:"`` for an
                ephemeral in-process index (useful in tests). Pass a directory path for a
                persistent store. If omitted or ``chromadb`` is not installed, the vector
                index is silently skipped — all other operations remain unaffected.
        """
        self._path = Path(db_path)
        self._retry_attempts = max(1, retry_attempts)
        self._retry_interval = retry_interval
        if self._path.parent and not self._path.parent.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        # WAL mode: concurrent readers + one writer, no exclusive write lock (T-03).
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        _migrate(self._conn)

        # Optional Chroma integration (FR-24, ADR-0007).
        self._chroma_collection: Any | None = None
        if chroma_path is not None:
            # In-memory mode uses a UUID-suffixed collection name so concurrent test
            # instances (which share a process-wide EphemeralClient singleton) remain
            # isolated. Disk mode uses the fixed name "assessments" for continuity.
            collection_name = (
                f"{_CHROMA_COLLECTION}_{uuid.uuid4().hex}"
                if chroma_path == _IN_MEMORY
                else _CHROMA_COLLECTION
            )
            self._chroma_collection = _open_chroma_collection(chroma_path, collection_name)

    def save(self, output: AssessmentOutputModel) -> int:
        """Persist an assessment to SQLite (and Chroma if available), returning the SQLite row id.

        SQLite is always written first; it is the canonical record. The Chroma write
        is best-effort — a failure logs a warning but does not raise so the primary
        persistence path is never interrupted.
        """
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                cursor = self._conn.execute(
                    "INSERT INTO assessments "
                    "(release, value_stream, verdict, score, generated_at, document) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        output.release,
                        output.value_stream,
                        output.verdict.value,
                        output.score,
                        output.generated_at.isoformat(),
                        output.model_dump_json(),
                    ),
                )
                self._conn.commit()
                rowid = cursor.lastrowid
                assert rowid is not None  # guaranteed after a successful INSERT
                if self._chroma_collection is not None:
                    _save_chroma(self._chroma_collection, rowid, output)
                return rowid
            except sqlite3.OperationalError as exc:
                last_error = exc
                if attempt < self._retry_attempts:
                    time.sleep(self._retry_interval)
        raise PersistenceError(
            f"failed to persist assessment after {self._retry_attempts} attempts: {last_error}"
        )

    def latest_for(self, release: str, value_stream: str) -> AssessmentOutputModel | None:
        """Return the most recent prior assessment for a release, or None."""
        row = self._conn.execute(
            "SELECT document FROM assessments WHERE release = ? AND value_stream = ? "
            "ORDER BY generated_at DESC, id DESC LIMIT 1",
            (release, value_stream),
        ).fetchone()
        if row is None:
            return None
        return AssessmentOutputModel.model_validate_json(row[0])

    def history(
        self, release: str, value_stream: str, *, limit: int = 10
    ) -> list[AssessmentOutputModel]:
        """Return up to ``limit`` assessments for a release, newest first."""
        rows = self._conn.execute(
            "SELECT document FROM assessments WHERE release = ? AND value_stream = ? "
            "ORDER BY generated_at DESC, id DESC LIMIT ?",
            (release, value_stream, limit),
        ).fetchall()
        return [AssessmentOutputModel.model_validate_json(row[0]) for row in rows]

    def similar_to(
        self, output: AssessmentOutputModel, *, k: int = 3
    ) -> list[AssessmentOutputModel]:
        """Return the ``k`` most similar past assessments by 6D score embedding (FR-24, ADR-0007).

        Similarity is cosine distance over [scope, estimation, environment, test_readiness,
        dependency, overall_score/100]. Returns an empty list if Chroma is not available or
        no records have been indexed yet.
        """
        if self._chroma_collection is None:
            return []
        embedding = _make_embedding(output)
        try:
            results = self._chroma_collection.query(
                query_embeddings=[embedding],
                n_results=k,
                include=["metadatas"],
            )
        except Exception:
            # Chroma is best-effort — never let it crash the pipeline.
            logger.warning("Chroma query failed; returning empty similar_to result.", exc_info=True)
            return []

        metadatas = results.get("metadatas", [[]])[0]
        assessments: list[AssessmentOutputModel] = []
        for meta in metadatas:
            doc_json = meta.get("document")
            if doc_json:
                try:
                    assessments.append(AssessmentOutputModel.model_validate_json(doc_json))
                except Exception:
                    logger.warning(
                        "Failed to deserialise Chroma document; skipping.", exc_info=True
                    )
        return assessments

    def all_recent(
        self, value_stream: str | None = None, *, limit: int = 50
    ) -> list[AssessmentOutputModel]:
        """Return up to ``limit`` most recent assessments across all releases, newest first.

        Pass ``value_stream`` to scope the result to one stream; omit for all
        streams.  Used by the dashboard history panel (ADR-0020) to populate the
        activity feed without needing to know which releases exist in advance.

        Args:
            value_stream: If given, only assessments for this stream are returned.
            limit: Maximum number of records to return (default 50).
        """
        if value_stream is not None:
            rows = self._conn.execute(
                "SELECT document FROM assessments WHERE value_stream = ? "
                "ORDER BY generated_at DESC, id DESC LIMIT ?",
                (value_stream, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT document FROM assessments ORDER BY generated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AssessmentOutputModel.model_validate_json(row[0]) for row in rows]

    def assessed_releases(self, value_stream: str | None = None) -> list[str]:
        """Return distinct release names that have at least one assessment, alphabetically.

        Pass ``value_stream`` to scope the result to one stream; omit for all streams.
        Used by the Trends panel to populate the release-selector dropdown with only
        releases that actually have history to chart (ADR-0020).

        Args:
            value_stream: If given, only releases for this stream are returned.
        """
        if value_stream is not None:
            rows = self._conn.execute(
                "SELECT DISTINCT release FROM assessments WHERE value_stream = ? ORDER BY release",
                (value_stream,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT DISTINCT release FROM assessments ORDER BY release"
            ).fetchall()
        return [row[0] for row in rows]

    def close(self) -> None:
        """Close the SQLite connection and release the file handle.

        Call this when the store is no longer needed. ``run_and_record`` in
        ``pipeline.py`` closes the store it creates in a finally block so the
        connection is always released even if persistence fails.
        """
        self._conn.close()


# Backward-compatibility alias — existing code that imports AssessmentStore continues to work.
AssessmentStore = SQLiteAssessmentStore


# ---------------------------------------------------------------------------
# Chroma helpers — isolated so the import failure path is easy to follow
# ---------------------------------------------------------------------------


def _open_chroma_collection(chroma_path: str, collection_name: str) -> Any | None:
    """Open (or create) a Chroma collection at ``chroma_path`` with ``collection_name``.

    Returns the collection on success, or ``None`` if ``chromadb`` is not
    installed. The ``":memory:"`` sentinel creates an ephemeral (in-process)
    client — used in tests so no files are created on disk.
    """
    try:
        import chromadb
    except ImportError:
        logger.info("chromadb not installed; Chroma RAG index disabled (FR-24, ADR-0007).")
        return None

    try:
        if chroma_path == _IN_MEMORY:
            client = chromadb.EphemeralClient()
        else:
            client = chromadb.PersistentClient(path=chroma_path)
        return client.get_or_create_collection(
            name=collection_name,
            # cosine distance is more interpretable for normalised score vectors
            # than the default squared-L2 distance.
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        logger.warning("Failed to open Chroma collection; RAG index disabled.", exc_info=True)
        return None


def _save_chroma(collection: Any, rowid: int, output: AssessmentOutputModel) -> None:
    """Upsert an assessment into the Chroma collection (best-effort).

    The document ID is ``"row-<rowid>"`` to guarantee uniqueness across re-runs.
    The full JSON is stored in metadata so ``similar_to()`` can reconstruct the
    full ``AssessmentOutputModel`` without a round-trip to SQLite.
    """
    try:
        collection.upsert(
            ids=[f"row-{rowid}"],
            embeddings=[_make_embedding(output)],
            metadatas=[
                {
                    "release": output.release,
                    "value_stream": output.value_stream,
                    "verdict": output.verdict.value,
                    "score": output.score,
                    # Full JSON in metadata — Chroma metadata values must be str/int/float/bool.
                    "document": output.model_dump_json(),
                }
            ],
        )
    except Exception:
        logger.warning("Failed to upsert assessment into Chroma; continuing.", exc_info=True)
