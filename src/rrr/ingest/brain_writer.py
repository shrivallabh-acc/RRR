"""Append or update a dated snapshot in a ``<value-stream>-history.json`` brain file.

The file format is the brain contract defined in ADR-0012.  ``BrainWriter`` is
idempotent: re-ingesting the same HTML (same generated date) overwrites that
snapshot without duplicating it.  Snapshots for other dates are left untouched so
the history accumulates across weekly report runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BrainWriter:
    """Reads, upserts, and writes a ``<value-stream>-history.json`` file."""

    def append_snapshot(
        self,
        brain_dir: Path,
        value_stream: str,
        date: str,
        releases: list[dict[str, Any]],
    ) -> Path:
        """Upsert a dated snapshot into the history file and return its path.

        If the brain file does not exist it is created from scratch.  If a
        snapshot for *date* already exists (same HTML re-ingested) it is replaced
        so the operation is safe to repeat.  All other snapshots are preserved.
        """
        brain_dir.mkdir(parents=True, exist_ok=True)
        path = brain_dir / f"{value_stream}-history.json"

        history = self._read(path, value_stream)

        # Upsert: remove any existing snapshot for this date, then add the new one.
        history["snapshots"] = [s for s in history["snapshots"] if s.get("date") != date]
        history["snapshots"].append({"date": date, "releases": releases})

        # Keep snapshots in chronological order.
        history["snapshots"].sort(key=lambda s: s["date"])

        path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    # ------------------------------------------------------------------

    @staticmethod
    def _read(path: Path, value_stream: str) -> dict[str, Any]:
        """Load the existing history file, or return an empty history skeleton."""
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        return {"value_stream": value_stream, "snapshots": []}
