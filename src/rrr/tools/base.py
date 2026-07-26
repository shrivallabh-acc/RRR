"""``BaseTool`` protocol and the runner result type (FR-10, NFR-7).

Tools are structural: anything with a ``name`` and an ``invoke(**params)`` satisfies
:class:`BaseTool`, so new tools are addable without touching assessors or core.
:class:`ToolRunResult` pairs a call's (arbitrary) output with the recorded
:class:`~rrr.models.evidence.ToolInvocationModel` for the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from rrr.models.evidence import ToolInvocationModel


@runtime_checkable
class BaseTool(Protocol):
    """A modular, recorded unit of work an assessor can invoke."""

    @property
    def name(self) -> str:
        """Stable identifier recorded on every invocation."""
        ...

    def invoke(self, **params: Any) -> Any:
        """Execute the tool and return its (tool-specific) output."""
        ...


@dataclass(frozen=True)
class ToolRunResult:
    """A successful tool call: its output plus the recorded invocation."""

    output: Any
    invocation: ToolInvocationModel
