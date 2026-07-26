"""``RKTBrainReader`` — reads the normalized brain extract (FR-10, ADR-0012).

Loads ``<brain_dir>/<value_stream>-history.json``, validates it against
:class:`~rrr.models.brain.BrainHistory`, selects a snapshot (latest by default or
a specific ISO date) and a release (``ir_name``), and returns a
:class:`BrainReadResult`. It also exposes the per-release **planned-SP history**
across snapshots so the Scope assessor can detect scope creep (ADR-0013) without
re-reading the file. This is the anti-corruption boundary: assessors see only this
result, never the raw report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from rrr.errors import BrainReadError
from rrr.models.base import RRRModel
from rrr.models.brain import BrainHistory, BrainSnapshot, ReleaseRecord

TOOL_NAME = "rkt_brain_reader"
LATEST = "latest"


class PlannedSPPoint(RRRModel):
    """One snapshot's planned story points for a release (scope-creep series)."""

    date: str
    total: int = Field(ge=0)


class BrainReadResult(RRRModel):
    """The selected release plus the context an assessor needs."""

    value_stream: str
    snapshot_date: str
    release: ReleaseRecord
    planned_sp_history: list[PlannedSPPoint] = Field(default_factory=list)


class RKTBrainReader:
    """Reads one value stream's history file and selects a release."""

    def __init__(self, brain_dir: str | Path) -> None:
        self._dir = Path(brain_dir)

    @property
    def name(self) -> str:
        return TOOL_NAME

    def invoke(self, **params: Any) -> BrainReadResult:
        """BaseTool entry point — delegates to the typed :meth:`read` (FR-10)."""
        if "value_stream" not in params:
            raise BrainReadError("RKTBrainReader requires a 'value_stream' parameter")
        return self.read(
            value_stream=params["value_stream"],
            snapshot=params.get("snapshot", LATEST),
            ir_name=params.get("ir_name"),
            programme=params.get("programme"),
        )

    def read(
        self,
        *,
        value_stream: str,
        snapshot: str = LATEST,
        ir_name: str | None = None,
        programme: str | None = None,
    ) -> BrainReadResult:
        """Typed read: load the history file, select a snapshot and release.

        ``programme`` narrows the candidate pool for fuzzy matching when ``ir_name``
        is a partial string that would otherwise match releases from multiple
        programmes (e.g. "Fund to Fund" matching both an OSM and an AIMS release).
        """
        history = self._load(value_stream)
        chosen = self._select_snapshot(history, snapshot)
        release = self._select_release(chosen, ir_name, programme=programme)
        return BrainReadResult(
            value_stream=history.value_stream,
            snapshot_date=chosen.date,
            release=release,
            planned_sp_history=self._planned_sp_history(history, release.ir_name),
        )

    def _load(self, value_stream: str) -> BrainHistory:
        """Read and validate the value-stream history JSON from disk.

        The filename convention is ``<value_stream>-history.json`` inside the
        brain directory (ADR-0012). We validate through Pydantic so any schema
        mismatch surfaces as a clear BrainReadError rather than an AttributeError
        deep inside an assessor.
        """
        path = self._dir / f"{value_stream}-history.json"
        if not path.is_file():
            raise BrainReadError(f"brain file not found for value stream {value_stream!r}: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BrainReadError(f"brain file is not valid JSON: {path}: {exc}") from exc
        try:
            return BrainHistory.model_validate(raw)
        except ValidationError as exc:
            raise BrainReadError(f"brain file failed validation: {path}: {exc}") from exc

    @staticmethod
    def _select_snapshot(history: BrainHistory, snapshot: str) -> BrainSnapshot:
        """Pick the right snapshot from the history.

        ``"latest"`` selects the snapshot with the highest ISO date string — ISO
        dates sort correctly as strings so no date parsing is needed. A specific
        date string selects an exact match. A missing date raises so the caller
        gets a list of what IS available, making config errors easy to diagnose.
        """
        if snapshot == LATEST:
            return max(history.snapshots, key=lambda s: s.date)
        for snap in history.snapshots:
            if snap.date == snapshot:
                return snap
        available = ", ".join(sorted(s.date for s in history.snapshots))
        raise BrainReadError(f"snapshot {snapshot!r} not found; available dates: {available}")

    @staticmethod
    def _select_release(
        snapshot: BrainSnapshot,
        ir_name: str | None,
        *,
        programme: str | None = None,
    ) -> ReleaseRecord:
        """Pick a specific release from the snapshot by its ir_name.

        Match order: (1) exact, (2) case-insensitive exact, (3) case-insensitive
        substring. Multiple substring matches are surfaced as an error so the caller
        can narrow the query. If ``ir_name`` is None we auto-select only when the
        snapshot has exactly one release — if there are multiple and no name is given
        we raise, because silently assessing the wrong release is worse than an error.

        ``programme`` pre-filters the candidate list before matching, which resolves
        ambiguity when the same partial name exists in multiple programmes
        (e.g. ``"Fund to Fund"`` matching both OSM and AIMS releases).
        """
        releases = snapshot.releases

        # Narrow candidates to the requested programme when supplied.
        if programme is not None:
            prog_lower = programme.lower()
            releases = [r for r in releases if r.programme.lower() == prog_lower]

        if ir_name is None:
            if len(releases) == 1:
                return releases[0]
            names = "\n  ".join(r.ir_name for r in releases)
            raise BrainReadError(
                f"snapshot has {len(releases)} releases — specify --release. Available:\n  {names}"
            )

        # Exact match.
        for release in releases:
            if release.ir_name == ir_name:
                return release

        # Case-insensitive exact match.
        query_lower = ir_name.lower()
        for release in releases:
            if release.ir_name.lower() == query_lower:
                return release

        # Case-insensitive substring match — user may not know the full name.
        partial = [r for r in releases if query_lower in r.ir_name.lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            matched = "\n  ".join(r.ir_name for r in partial)
            raise BrainReadError(
                f"{len(partial)} releases match {ir_name!r} — be more specific:\n  {matched}"
            )

        # No match at all — list everything so the user can copy-paste.
        available = "\n  ".join(r.ir_name for r in releases)
        raise BrainReadError(f"no release matches {ir_name!r}. Available releases:\n  {available}")

    def list_releases(
        self,
        value_stream: str,
        snapshot: str = LATEST,
        *,
        programme: str | None = None,
    ) -> list[ReleaseRecord]:
        """Return release records for a value stream snapshot, optionally filtered by programme.

        Returns full :class:`ReleaseRecord` objects so callers can display programme
        codes and dependency relationships alongside the release name.  Pass
        ``programme="OSM"`` to see only native OSM releases, ``programme="AIMS"`` for
        AIMS releases, etc.  ``None`` returns all releases.
        """
        history = self._load(value_stream)
        chosen = self._select_snapshot(history, snapshot)
        releases = chosen.releases
        if programme is not None:
            prog_lower = programme.lower()
            releases = [r for r in releases if r.programme.lower() == prog_lower]
        return list(releases)

    def list_snapshot_dates(
        self,
        value_stream: str,
        *,
        ir_name: str | None = None,
    ) -> list[str]:
        """Return all snapshot dates for a value stream, sorted oldest → newest.

        When ``ir_name`` is given, only dates where that release appears are
        included — a release may be absent from early snapshots if it was added
        mid-programme.  Used by the Trends panel to build the chart x-axis from
        brain history rather than from SQLite assessment runs.
        """
        try:
            history = self._load(value_stream)
        except BrainReadError:
            return []
        dates: list[str] = []
        for snap in sorted(history.snapshots, key=lambda s: s.date):
            if ir_name is None or any(r.ir_name == ir_name for r in snap.releases):
                dates.append(snap.date)
        return dates

    def list_toc_value_streams(
        self,
        value_stream: str,
        snapshot: str = LATEST,
    ) -> list[str]:
        """Return the distinct TOC value-stream names present in the snapshot, sorted.

        Collects non-null ``toc_value_stream`` values across all releases in the
        selected snapshot.  Returns an empty list when the brain file is missing,
        when no releases are tagged (pre-ADR-0021 brain files), or when the
        snapshot has no TOC-tagged releases.

        The sorted order makes filter-button rendering deterministic in the UI.
        """
        try:
            history = self._load(value_stream)
        except BrainReadError:
            return []
        try:
            chosen = self._select_snapshot(history, snapshot)
        except BrainReadError:
            return []
        seen: set[str] = set()
        for r in chosen.releases:
            if r.toc_value_stream is not None:
                seen.add(r.toc_value_stream)
        return sorted(seen)

    @staticmethod
    def _planned_sp_history(history: BrainHistory, ir_name: str) -> list[PlannedSPPoint]:
        """Build the time-series of planned story points for a release across all snapshots.

        We scan every snapshot in chronological order and collect the planned SP
        total for the requested release wherever it appears. The result is a list
        of (date, total) points that the ScopeAssessor uses to detect scope creep —
        if planned SP grew significantly from the first to the last snapshot, the
        team added work mid-sprint (ADR-0013). The inner ``break`` stops scanning
        a single snapshot once the release is found to avoid double-counting.
        """
        points: list[PlannedSPPoint] = []
        for snap in sorted(history.snapshots, key=lambda s: s.date):
            for release in snap.releases:
                if release.ir_name == ir_name:
                    points.append(PlannedSPPoint(date=snap.date, total=release.summary.total))
                    break
        return points
