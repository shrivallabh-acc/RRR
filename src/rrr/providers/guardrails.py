"""Structured-output repair loop (ADR-0009 #2).

Text-generating providers (local LLM, Claude) call :func:`parse_with_repair` with
a ``generate`` callable. The raw output is validated against the response model;
on failure the loop retries once, feeding the validation error back as a repair
hint, then raises :class:`~rrr.errors.ProviderValidationError` so the caller can
degrade to the ``RuleBasedProvider`` with reduced confidence.

The rule-based provider does *not* use this — it constructs the model directly and
so cannot produce invalid output.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from rrr.errors import ProviderValidationError

ReasoningModel = TypeVar("ReasoningModel", bound=BaseModel)

# generate(repair_hint) -> raw JSON; repair_hint is None on the first attempt.
GenerateFn = Callable[[str | None], str]


def parse_with_repair(
    generate: GenerateFn,
    response_model: type[ReasoningModel],
    *,
    max_repairs: int = 1,
) -> ReasoningModel:
    """Generate, validate, and repair once; raise if still invalid.

    :param generate: produces raw JSON; receives the prior validation error (or None).
    :param response_model: the Pydantic model the output must satisfy.
    :param max_repairs: extra attempts after the first (default 1, per ADR-0009).
    """
    last_error: str | None = None
    attempts = max_repairs + 1
    for _ in range(attempts):
        raw = generate(last_error)
        try:
            return response_model.model_validate_json(raw)
        except ValidationError as exc:
            last_error = _summarize(exc)
    raise ProviderValidationError(
        f"structured output failed {response_model.__name__} validation "
        f"after {attempts} attempt(s); last error: {last_error}"
    )


def _summarize(exc: ValidationError) -> str:
    """Compact, model-feedable description of what was wrong."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
