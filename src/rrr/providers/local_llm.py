"""``LocalLLMProvider`` — on-machine LLM via Ollama HTTP (ADR-0006, ADR-0010).

Calls the Ollama ``/api/chat`` endpoint on ``127.0.0.1`` (local-first, Phase 1).
Uses stdlib ``urllib`` — no extra SDK dependency. The full guardrail chain applies:

    generate → parse_with_repair (1 repair retry) → ProviderValidationError
                                                           ↓
                                              RuleBasedProvider fallback
                                              (BaseAssessor.reason catches it)

Network and HTTP errors are caught here and re-raised as ``ProviderValidationError``
so the same fallback path handles them — a broken/absent Ollama gracefully degrades
rather than crashing the assessment.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from rrr.errors import ConfigurationError, ProviderValidationError
from rrr.providers.base import LLMProvider, ReasoningModel, ReasoningRequest
from rrr.providers.guardrails import parse_with_repair

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a release-readiness analyst. "
    "Respond ONLY with valid JSON that exactly matches the provided schema. "
    "Do not add explanation, markdown, or any text outside the JSON object."
)


class LocalLLMProvider(LLMProvider):
    """Ollama-backed provider for on-machine reasoning (Phase 1, local-first)."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost"),
        timeout: float = 30.0,
        repair_retries: int = 1,
    ) -> None:
        host = urlparse(endpoint).hostname or ""
        if host not in allowed_hosts:
            raise ConfigurationError(
                f"local_llm endpoint host {host!r} is not in the allow-list "
                f"{list(allowed_hosts)} — local-first only (ADR-0010)"
            )
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._repair_retries = repair_retries

    @property
    def name(self) -> str:
        return f"LocalLLMProvider({self._model})"

    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[ReasoningModel],
    ) -> ReasoningModel:
        """Call Ollama, validate output, repair once, then raise for fallback."""
        schema_hint = json.dumps(response_model.model_json_schema(), indent=2)

        def generate(repair_hint: str | None) -> str:
            return self._call_ollama(request, schema_hint, repair_hint)

        try:
            return parse_with_repair(generate, response_model, max_repairs=self._repair_retries)
        except ProviderValidationError:
            raise
        except Exception as exc:
            raise ProviderValidationError(
                f"{self.name} unexpected error during reasoning: {exc}"
            ) from exc

    # ------------------------------------------------------------------

    def _call_ollama(
        self,
        request: ReasoningRequest,
        schema_hint: str,
        repair_hint: str | None,
    ) -> str:
        """Send one chat request to Ollama and return the raw JSON string.

        We use ``format: "json"`` in the Ollama payload to ask the model to
        constrain its output to JSON, and ``stream: false`` so we get the full
        response in a single HTTP reply instead of a stream of tokens.

        All network problems (unreachable server, bad HTTP status, garbled body)
        are caught and re-raised as ProviderValidationError — the same error type
        that a validation failure raises — so the caller's fallback logic handles
        both cases identically without needing to know which went wrong.
        """
        messages = self._build_messages(request, schema_hint, repair_hint)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "format": "json",  # Ask Ollama to force JSON output mode.
            "stream": False,  # Get the full response at once, not a token stream.
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._endpoint}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data: dict[str, Any] = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            # HTTP 4xx/5xx — common when the model isn't loaded in Ollama.
            raise ProviderValidationError(
                f"{self.name} HTTP {exc.code} from Ollama — is the model loaded?"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            # Connection refused, DNS failure, socket timeout, etc.
            raise ProviderValidationError(
                f"{self.name} cannot reach Ollama at {self._endpoint}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            # Ollama returned something that isn't valid JSON at all.
            raise ProviderValidationError(
                f"{self.name} Ollama returned non-JSON response: {exc}"
            ) from exc

        # The Ollama /api/chat response wraps the model output in message.content.
        content: str = data.get("message", {}).get("content", "")
        if not content:
            raise ProviderValidationError(f"{self.name} Ollama response missing message.content")
        logger.debug("%s raw response: %s", self.name, content[:200])
        return content

    @staticmethod
    def _build_messages(
        request: ReasoningRequest,
        schema_hint: str,
        repair_hint: str | None,
    ) -> list[dict[str, str]]:
        """Build the Ollama chat messages list from the reasoning request.

        The conversation has two or three turns:
        1. system — tells the model it is a JSON-only analyst.
        2. user   — the full context: dimension, summary, facts, risk factors,
                    allowed classifications, and the required JSON schema.
        3. user (optional) — added only on a repair attempt; tells the model what
                    was wrong with its previous response so it can correct it.

        Separating the schema from the system prompt (putting it in the user turn)
        keeps the system prompt short and avoids confusing the model with a very
        long system instruction. The JSON schema is sent every time so the model
        always has the target structure in front of it.
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

        user_content = "\n\n".join(parts)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        if repair_hint:
            # On a repair attempt, append the validation error so the model can fix it.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The previous response failed JSON schema validation: {repair_hint}\n"
                        "Fix the issues and respond again with ONLY the corrected JSON object."
                    ),
                }
            )
        return messages
