"""ClaudeProvider — Anthropic Messages API via the anthropic SDK (Phase 2, ADR-0006).

Makes external calls to ``api.anthropic.com`` — intentionally breaks the local-first
constraint (ADR-0010). Only use when ``ANTHROPIC_API_KEY`` is set in the environment.

The full guardrail chain applies identically to the local providers:

    messages.create() → parse_with_repair (1 repair retry) → ProviderValidationError
                                                                    ↓
                                                         RuleBasedProvider fallback
                                                         (BaseAssessor.reason catches it)

``anthropic`` is imported lazily inside ``__init__`` so the package stays importable
without it. Install with ``pip install rrr[cloud]``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from rrr.errors import ConfigurationError, ProviderValidationError
from rrr.providers.base import LLMProvider, ReasoningModel, ReasoningRequest
from rrr.providers.guardrails import parse_with_repair

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a release-readiness analyst. "
    "Respond ONLY with valid JSON that exactly matches the provided schema. "
    "Do not add explanation, markdown, or any text outside the JSON object."
)


class ClaudeProvider(LLMProvider):
    """Anthropic Claude Messages API provider — Phase 2 external scale-out (ADR-0006)."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        repair_retries: int = 1,
    ) -> None:
        """Initialise the provider and create an Anthropic client.

        :param model: Anthropic model ID, e.g. ``"claude-opus-4-8"`` or ``"claude-sonnet-4-6"``.
        :param api_key: Anthropic API key. Defaults to the ``ANTHROPIC_API_KEY`` env var.
        :param max_tokens: Maximum output tokens per call (limits cost and latency).
        :param temperature: Sampling temperature — keep low (≤ 0.2) for structured JSON output.
        :param repair_retries: Extra attempts after the first failure (ADR-0009 default 1).
        :raises ConfigurationError: if the ``anthropic`` package is not installed or no API
            key is found in the argument or ``ANTHROPIC_API_KEY`` environment variable.
        """
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ConfigurationError(
                "provider.type is 'claude' but the anthropic package is not installed — "
                "run: pip install rrr[cloud]"
            ) from exc
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ConfigurationError(
                "ClaudeProvider requires an API key — set the ANTHROPIC_API_KEY "
                "environment variable or pass api_key= explicitly."
            )
        self._client: Any = _anthropic.Anthropic(api_key=resolved_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._repair_retries = repair_retries

    @property
    def name(self) -> str:
        """Provider id recorded in the audit trail (FR-25)."""
        return f"ClaudeProvider({self._model})"

    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[ReasoningModel],
    ) -> ReasoningModel:
        """Call Claude Messages API, validate output, repair once, then raise for fallback."""
        schema_hint = json.dumps(response_model.model_json_schema(), indent=2)

        def generate(repair_hint: str | None) -> str:
            return self._call_claude(request, schema_hint, repair_hint)

        try:
            return parse_with_repair(generate, response_model, max_repairs=self._repair_retries)
        except ProviderValidationError:
            raise
        except Exception as exc:
            raise ProviderValidationError(
                f"{self.name} unexpected error during reasoning: {exc}"
            ) from exc

    # ------------------------------------------------------------------

    def _call_claude(
        self,
        request: ReasoningRequest,
        schema_hint: str,
        repair_hint: str | None,
    ) -> str:
        """Send one request to the Anthropic Messages API and return the raw text.

        Uses the system + single-user-turn pattern: the system prompt enforces
        JSON-only output; the user turn carries the full reasoning context, schema,
        and — on a repair attempt — the validation error from the previous call.

        All Anthropic SDK errors (auth failure, rate-limit, network error, model
        unavailable) are caught and re-raised as ProviderValidationError so the
        caller's fallback logic handles both API errors and validation failures
        identically — a broken network degrades gracefully to RuleBasedProvider.
        """
        user_message = self._build_user_message(request, schema_hint, repair_hint)
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            # Catches AuthenticationError, RateLimitError, APIConnectionError,
            # APIStatusError, etc. Re-raise so the fallback path handles it the
            # same as a validation failure — no special casing per error type.
            raise ProviderValidationError(f"{self.name} Anthropic API call failed: {exc}") from exc

        if not message.content:
            raise ProviderValidationError(
                f"{self.name} Anthropic response contained no content blocks"
            )
        # message.content is a list of ContentBlock objects; TextBlock has a .text attribute.
        text: str = getattr(message.content[0], "text", "")
        if not text:
            raise ProviderValidationError(
                f"{self.name} Anthropic response first content block has no text"
            )
        logger.debug("%s raw response: %s", self.name, text[:200])
        return text

    @staticmethod
    def _build_user_message(
        request: ReasoningRequest,
        schema_hint: str,
        repair_hint: str | None,
    ) -> str:
        """Build the single user-turn text from the reasoning request.

        Everything goes into one user message so the prompt works without needing
        an alternating assistant reply. On a repair attempt the validation error is
        appended at the end so the model sees exactly what went wrong and can
        correct its output.
        """
        parts: list[str] = []
        if request.dimension:
            parts.append(f"Dimension: {request.dimension.value}")
        if request.summary:
            parts.append(f"Summary: {request.summary}")
        if request.classification:
            parts.append(f"Pre-computed classification: {request.classification}")
        if request.facts:
            facts_block = "\n".join(f"  - {f}" for f in request.facts)
            parts.append(f"Observations:\n{facts_block}")
        if request.risk_factors:
            rf_lines = "\n".join(
                f"  - [{rf.severity.value}] {rf.description}" for rf in request.risk_factors
            )
            parts.append(f"Risk factors:\n{rf_lines}")
        if request.allowed_classifications:
            parts.append(f"Allowed classification values: {request.allowed_classifications}")
        parts.append(f"Required JSON schema:\n{schema_hint}")
        parts.append("Respond ONLY with a valid JSON object matching the schema above.")
        if repair_hint:
            # Append the validation error so the model knows exactly what to fix.
            parts.append(
                f"IMPORTANT: A previous response failed JSON schema validation: {repair_hint}\n"
                "Fix the issues and return ONLY the corrected JSON object."
            )
        return "\n\n".join(parts)
