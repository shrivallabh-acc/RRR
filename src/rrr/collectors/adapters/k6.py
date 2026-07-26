"""k6 adapter — reads a k6 summary-export JSON file and maps load-test results to PerformanceInput.

This is a file-based adapter (no network call, no credentials) that reads the JSON
summary written by k6's ``--summary-export`` flag and returns a partial dict for the
``performance`` dimension. ``CollectorRunner.run()`` validates the dict against
``PerformanceInput`` before writing ``data/performance.json``.

Typical k6 invocation that produces the expected input file::

    k6 run load-test.js --summary-export=k6-summary.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rrr.collectors.base import BaseCollector, CollectorConfig


class K6AdapterError(Exception):
    """Raised when the k6 summary file cannot be read or parsed."""


class K6Adapter(BaseCollector):
    """Reads a k6 ``--summary-export`` JSON file and maps metrics to PerformanceInput fields.

    The adapter is intentionally narrow: it populates only the fields it can derive
    from the k6 summary format (``performance_test_status``, ``p99_latency_ms``).
    The caller sets ``slo_p99_threshold_ms`` and ``capacity_headroom_pct`` either
    interactively or via a separate data source.

    Fields populated:

    - ``performance_test_status``: ``"passed"`` when no k6 check thresholds are
      breached (``checks.values.fails == 0``); ``"failed"`` otherwise.
    - ``p99_latency_ms``: extracted from
      ``metrics.http_req_duration.values["p(99)"]`` when present.

    Fields *not* populated (left to InputContract defaults):

    - ``slo_p99_threshold_ms`` — set this manually or via config.
    - ``capacity_headroom_pct`` — k6 does not report capacity headroom directly.
    """

    def __init__(self, summary_path: Path | str) -> None:
        """Bind the adapter to a k6 summary-export file path.

        Args:
            summary_path: Path to the JSON summary written by k6's
                ``--summary-export`` flag.  The file must exist when
                ``collect()`` is called.
        """
        self._summary_path = Path(summary_path)

    @property
    def dimension(self) -> str:
        """Return the target dimension name for this adapter."""
        return "performance"

    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Read the k6 summary file and return a partial PerformanceInput dict.

        Parses the k6 summary JSON and derives ``performance_test_status`` from the
        ``checks`` metric and ``p99_latency_ms`` from ``http_req_duration``.  Fields
        that k6 does not report are omitted so the InputContract defaults take effect.

        Args:
            config: Runtime context provided by ``CollectorRunner``.  Not used by
                this file-based adapter but required by the ``BaseCollector`` contract.

        Returns:
            Partial dict ready for ``PerformanceInput.model_validate()``.

        Raises:
            K6AdapterError: If the summary file is missing or contains invalid JSON.
        """
        raw = self._load_summary()
        metrics = raw.get("metrics", {})

        status = self._derive_status(metrics)
        result: dict[str, Any] = {"performance_test_status": status}

        p99 = self._extract_p99(metrics)
        if p99 is not None:
            result["p99_latency_ms"] = p99

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_summary(self) -> dict[str, Any]:
        """Read and parse the k6 summary file.

        Raises:
            K6AdapterError: If the file is absent, unreadable, or not valid JSON.
        """
        if not self._summary_path.exists():
            raise K6AdapterError(
                f"k6 summary file not found: {self._summary_path}. "
                "Run k6 with --summary-export=<path> to generate it."
            )
        try:
            content = self._summary_path.read_text(encoding="utf-8")
            result: dict[str, Any] = json.loads(content)
            return result
        except (OSError, json.JSONDecodeError) as exc:
            raise K6AdapterError(
                f"Failed to read k6 summary at {self._summary_path}: {exc}"
            ) from exc

    @staticmethod
    def _derive_status(metrics: dict[str, Any]) -> str:
        """Map k6 check metrics to a PerformanceTestStatus string value.

        k6 increments ``checks.values.fails`` for every threshold breach.
        Zero failures → ``"passed"``; any failures → ``"failed"``.
        A missing ``checks`` block is treated as no checks defined → ``"passed"``.
        """
        fails = (
            metrics.get("checks", {})
                   .get("values", {})
                   .get("fails", 0)
        )
        return "failed" if fails > 0 else "passed"

    @staticmethod
    def _extract_p99(metrics: dict[str, Any]) -> float | None:
        """Extract the P99 latency in milliseconds from the http_req_duration metric.

        Returns None when the metric is absent (e.g., non-HTTP load tests or
        k6 scripts that disable the built-in HTTP metrics).
        """
        raw_p99 = (
            metrics.get("http_req_duration", {})
                   .get("values", {})
                   .get("p(99)")
        )
        if raw_p99 is None:
            return None
        return float(raw_p99)
