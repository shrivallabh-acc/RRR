"""``ToolRunner`` — timeout enforcement + invocation recording (FR-11).

Every tool call runs through the runner, which times it, truncates a summary,
and produces a :class:`~rrr.models.evidence.ToolInvocationModel`. On success it
returns a :class:`ToolRunResult`; on timeout or error it raises
``ToolTimeoutError`` / ``ToolInvocationError`` — each carrying the failed
invocation record so the caller can still audit the attempt.

Timeouts use a worker thread (FR-11). Python cannot forcibly kill a thread, so a
timed-out tool's thread is abandoned as a daemon; the runner stops waiting and
reports the timeout. Tools doing I/O should therefore also set their own
client-level timeout (e.g. the 10s source fetch, FR-3).
"""

from __future__ import annotations

import threading
from time import perf_counter
from typing import Any

from rrr.errors import ToolInvocationError, ToolTimeoutError
from rrr.models.evidence import EvidenceValue, ToolInvocationModel
from rrr.tools.base import BaseTool, ToolRunResult

DEFAULT_TOOL_TIMEOUT = 30.0
_SUMMARY_MAX = 500


def _coerce_params(params: dict[str, Any]) -> dict[str, EvidenceValue]:
    """Reduce params to JSON-scalar values for the audit record (non-scalars stringified)."""
    coerced: dict[str, EvidenceValue] = {}
    for key, value in params.items():
        scalar = value is None or isinstance(value, (str, int, float, bool))
        coerced[key] = value if scalar else str(value)
    return coerced


class ToolRunner:
    """Runs tools with a timeout and records each invocation."""

    def __init__(
        self,
        default_timeout: float = DEFAULT_TOOL_TIMEOUT,
        retry_count: int = 0,
        retry_backoff_s: float = 0.0,
    ) -> None:
        """Initialise the runner.

        :param default_timeout: seconds before a tool call is declared timed-out.
        :param retry_count: how many extra attempts to make on ``ToolInvocationError``
            (0 = no retry, the safe default for tests).
        :param retry_backoff_s: seconds to sleep between retry attempts.
        """
        self.default_timeout = default_timeout
        self.retry_count = retry_count
        self.retry_backoff_s = retry_backoff_s

    def run(self, tool: BaseTool, *, timeout: float | None = None, **params: Any) -> ToolRunResult:
        """Invoke ``tool`` with ``params`` under a timeout, recording the call.

        :raises ToolTimeoutError: if the call exceeds the timeout.
        :raises ToolInvocationError: if the tool raises during execution.
        """
        limit = self.default_timeout if timeout is None else timeout
        recorded_params = _coerce_params(params)
        box: dict[str, Any] = {}

        def _target() -> None:
            try:
                box["output"] = tool.invoke(**params)
            except BaseException as exc:  # noqa: BLE001 (re-raised on caller thread)
                box["error"] = exc

        worker = threading.Thread(target=_target, name=f"tool-{tool.name}", daemon=True)
        start = perf_counter()
        worker.start()
        worker.join(limit)
        duration_ms = int((perf_counter() - start) * 1000)

        if worker.is_alive():
            invocation = self._record(
                tool.name,
                recorded_params,
                success=False,
                duration_ms=duration_ms,
                error_reason=f"timeout after {limit:.1f}s",
            )
            raise ToolTimeoutError(f"tool {tool.name!r} timed out after {limit:.1f}s", invocation)

        if "error" in box:
            error = box["error"]
            invocation = self._record(
                tool.name,
                recorded_params,
                success=False,
                duration_ms=duration_ms,
                error_reason=f"{type(error).__name__}: {error}",
            )
            raise ToolInvocationError(f"tool {tool.name!r} failed: {error}", invocation) from error

        output = box.get("output")
        invocation = self._record(
            tool.name,
            recorded_params,
            success=True,
            duration_ms=duration_ms,
            output_summary=str(output)[:_SUMMARY_MAX],
        )
        return ToolRunResult(output=output, invocation=invocation)

    @staticmethod
    def _record(
        name: str,
        params: dict[str, EvidenceValue],
        *,
        success: bool,
        duration_ms: int,
        output_summary: str = "",
        error_reason: str | None = None,
    ) -> ToolInvocationModel:
        """Create the audit record for one tool call (FR-11, NFR-3).

        Called for every outcome — success, timeout, and error — so the audit
        trail always has an entry even when the tool did not return a result.
        The output_summary is capped at 500 characters by the model's max_length
        constraint to keep records compact and database-friendly.
        """
        return ToolInvocationModel(
            name=name,
            params=params,
            output_summary=output_summary,
            success=success,
            duration_ms=duration_ms,
            error_reason=error_reason,
        )
