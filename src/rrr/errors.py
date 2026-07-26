"""Central exception hierarchy for RRR.

A single base (``RRRError``) so callers can catch everything RRR-raised, with
specific subclasses per failure domain. Tool/provider errors (FR-11, FR-23) are
added here as those layers land.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rrr.models.evidence import ToolInvocationModel


class RRRError(Exception):
    """Base class for all RRR-raised errors."""


class ConfigurationError(RRRError):
    """Raised when configuration fails to load, merge, or validate (FR-15).

    Carries the individual validation problems so the CLI can print a readable
    list rather than a raw Pydantic traceback.
    """

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        """Build the error, appending the individual validation problems to the message.

        When ``errors`` is provided (e.g. field-pathed Pydantic problems) they are
        bullet-listed below the headline message so a user running ``rrr`` sees
        exactly which config keys to fix, not a raw exception traceback.
        """
        self.errors: list[str] = errors or []
        if self.errors:
            detail = "\n".join(f"  - {e}" for e in self.errors)
            super().__init__(f"{message}\n{detail}")
        else:
            super().__init__(message)


class ToolError(RRRError):
    """Base for tool-execution failures (FR-11).

    Carries the (failed) ``ToolInvocationModel`` so the calling assessor can still
    record the attempt in its audit trail even though execution did not succeed.
    """

    def __init__(self, message: str, invocation: ToolInvocationModel | None = None) -> None:
        self.invocation = invocation
        super().__init__(message)


class ToolTimeoutError(ToolError):
    """Raised when a tool exceeds its timeout (FR-11)."""


class ToolInvocationError(ToolError):
    """Raised when a tool raises during execution (FR-11)."""


class BrainReadError(RRRError):
    """Raised when the requested value-stream file, snapshot, or release is not found (ADR-0012)."""


class SourceReadError(RRRError):
    """Raised when an env/dependency source can't be read or is non-local (FR-3/FR-5, NFR-8)."""


class PersistenceError(RRRError):
    """Raised when an assessment cannot be persisted after the retry budget (FR-14)."""


class ProviderError(RRRError):
    """Base for LLM-provider failures (ADR-0006, ADR-0009)."""


class ProviderValidationError(ProviderError):
    """Structured output failed schema validation after the repair retry (ADR-0009).

    The caller degrades to the ``RuleBasedProvider`` with reduced confidence.
    """
