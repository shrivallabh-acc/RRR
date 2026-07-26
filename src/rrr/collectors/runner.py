"""CollectorRunner — shared business logic for data freshness checks and collection runs.

The runner is the framework-agnostic core of the collection system (ADR-0023 Layer 1).
It is called identically from the ``rrr-collect`` CLI and the ``rrr-ui`` Collect screen,
keeping all business logic in one testable class rather than duplicated in each surface.

Two responsibilities:
  1. ``status()`` — scan ``data/`` for per-dimension JSON files and report freshness.
  2. ``run()`` — call a collector, validate the result against the dimension's
     ``InputContract``, and write the validated JSON to disk.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rrr.collectors.base import BaseCollector, CollectorConfig, CollectorResult
from rrr.models.base import InputContract, iso_millis


class CollectorStatus(enum.Enum):
    """Freshness state of a dimension's data file."""

    FRESH = "fresh"      # captured_at within staleness_days
    STALE = "stale"      # file exists but captured_at is too old or absent
    MISSING = "missing"  # file does not exist at all


@dataclass
class DimensionStatusReport:
    """Freshness summary for one dimension's data file.

    ``age_days`` is None when the file is missing or the timestamp is absent.
    ``file_path`` is None when the file does not exist.
    """

    dimension: str
    status: CollectorStatus
    file_path: Path | None
    age_days: float | None


class CollectorRunner:
    """Checks dimension data freshness and orchestrates collector runs (ADR-0023).

    The runner owns the write path: it validates collector output against the
    dimension's ``InputContract``, stamps ``captured_at``, and writes JSON.
    Collectors themselves never write files.
    """

    def __init__(self, staleness_days: int = 7) -> None:
        """Initialise with a configurable staleness threshold.

        Args:
            staleness_days: A file is considered FRESH if its ``captured_at``
                timestamp is within this many days of now. Default is 7.
        """
        self._staleness_days = staleness_days

    def status(
        self,
        dimensions: list[str],
        data_dir: Path,
    ) -> list[DimensionStatusReport]:
        """Scan ``data_dir`` for each dimension's JSON file and return freshness reports.

        A file is FRESH if it exists and its ``captured_at`` field is within
        ``staleness_days`` of now. STALE if the file exists but is outdated or
        has no timestamp. MISSING if the file does not exist.

        Args:
            dimensions: List of dimension name strings (``DimensionName.value``).
            data_dir: Directory containing ``<dimension>.json`` files.

        Returns:
            One ``DimensionStatusReport`` per requested dimension, in input order.
        """
        reports: list[DimensionStatusReport] = []
        now = datetime.now(UTC)
        for dim in dimensions:
            path = data_dir / f"{dim}.json"
            if not path.exists():
                reports.append(DimensionStatusReport(dim, CollectorStatus.MISSING, None, None))
                continue

            age_days: float | None = None
            status = CollectorStatus.STALE
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                captured_at = raw.get("captured_at")
                if captured_at:
                    dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                    age_days = (now - dt).total_seconds() / 86400.0
                    status = (
                        CollectorStatus.FRESH
                        if age_days <= self._staleness_days
                        else CollectorStatus.STALE
                    )
            except (json.JSONDecodeError, ValueError, OSError):
                # Treat unreadable or unparseable files as MISSING to prompt recollection.
                status = CollectorStatus.MISSING

            reports.append(DimensionStatusReport(dim, status, path, age_days))
        return reports

    def run(
        self,
        dimension: str,
        collector: BaseCollector,
        config: CollectorConfig,
        model_class: type[InputContract],
    ) -> CollectorResult:
        """Collect data for ``dimension``, validate it, and write to ``data_dir``.

        Calls ``collector.collect(config)``, validates the raw dict against
        ``model_class``, stamps ``captured_at`` if absent, then writes the
        validated JSON to ``config.data_dir/<dimension>.json``.

        Args:
            dimension: Dimension name string (``DimensionName.value``).
            collector: A ``BaseCollector`` instance whose ``collect()`` is called.
            config: A ``CollectorConfig`` instance (release, data_dir, flags).
            model_class: The dimension's ``InputContract`` subclass for validation.

        Returns:
            A ``CollectorResult`` with the validated data and timestamp.

        Raises:
            pydantic.ValidationError: If the collected dict fails model validation.
            OSError: If the output file cannot be written.
        """
        raw: dict[str, Any] = collector.collect(config)

        # Stamp captured_at if the collector did not set it.
        if not raw.get("captured_at"):
            raw["captured_at"] = iso_millis(datetime.now(UTC))

        validated = model_class.model_validate(raw)
        serialised = validated.model_dump()

        output_path = config.data_dir / f"{dimension}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(serialised, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return CollectorResult(
            dimension=dimension,
            data=serialised,
            collected_at=serialised.get("captured_at", ""),
        )
