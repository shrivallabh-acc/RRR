"""BedrockProvider — Amazon Bedrock Converse API via boto3 (Phase 2, ADR-0019).

Makes external calls to AWS — intentionally breaks the local-first constraint
(ADR-0010). Only use when AWS credentials are available in the environment
(IAM role, ``aws configure``, AWS SSO token, or environment variables).

The full guardrail chain applies identically to the local providers:

    converse() → parse_with_repair (1 repair retry) → ProviderValidationError
                                                             ↓
                                                  RuleBasedProvider fallback
                                                  (BaseAssessor.reason catches it)

boto3 is imported lazily in ``__init__`` so the package stays importable without
it. Install with ``pip install rrr[bedrock]``.
"""

from __future__ import annotations

import json
import logging
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


class BedrockProvider(LLMProvider):
    """Amazon Bedrock Converse API provider — Phase 2, model-agnostic (ADR-0019)."""

    def __init__(
        self,
        model_id: str,
        *,
        region: str = "us-east-1",
        max_tokens: int = 1024,
        temperature: float = 0.1,
        repair_retries: int = 1,
    ) -> None:
        """Initialise the provider and create a boto3 Bedrock runtime client.

        :param model_id: Bedrock modelId string, e.g.
            ``"anthropic.claude-3-5-sonnet-20241022-v2:0"`` or ``"amazon.titan-text-g1-express"``.
        :param region: AWS region where the model is available.
        :param max_tokens: Maximum output tokens per call (limits cost and latency).
        :param temperature: Sampling temperature — keep low (≤ 0.2) for structured JSON output.
        :param repair_retries: Extra attempts after the first failure (ADR-0009 default 1).
        :raises ConfigurationError: if boto3 is not installed.
        """
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ConfigurationError(
                "provider.type is 'bedrock' but boto3 is not installed — "
                "run: pip install rrr[bedrock]"
            ) from exc
        self._client: Any = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._repair_retries = repair_retries

    @property
    def name(self) -> str:
        """Provider id recorded in the audit trail (FR-25)."""
        return f"BedrockProvider({self._model_id})"

    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[ReasoningModel],
    ) -> ReasoningModel:
        """Call Bedrock Converse, validate output, repair once, then raise for fallback."""
        schema_hint = json.dumps(response_model.model_json_schema(), indent=2)

        def generate(repair_hint: str | None) -> str:
            return self._call_bedrock(request, schema_hint, repair_hint)

        try:
            return parse_with_repair(generate, response_model, max_repairs=self._repair_retries)
        except ProviderValidationError:
            raise
        except Exception as exc:
            raise ProviderValidationError(
                f"{self.name} unexpected error during reasoning: {exc}"
            ) from exc

    # ------------------------------------------------------------------

    def _call_bedrock(
        self,
        request: ReasoningRequest,
        schema_hint: str,
        repair_hint: str | None,
    ) -> str:
        """Send one request to the Bedrock Converse API and return the raw text.

        Uses the model-agnostic Converse API so the modelId can be changed in
        config without touching this code. All AWS SDK errors (access denied,
        throttling, network failure, missing credentials) are caught and
        re-raised as ProviderValidationError so the caller's fallback logic
        handles both API errors and validation failures identically.
        """
        message = self._build_user_message(request, schema_hint, repair_hint)
        try:
            response = self._client.converse(
                modelId=self._model_id,
                messages=[{"role": "user", "content": [{"text": message}]}],
                system=[{"text": _SYSTEM_PROMPT}],
                inferenceConfig={
                    "maxTokens": self._max_tokens,
                    "temperature": self._temperature,
                },
            )
        except Exception as exc:
            # Catches ClientError (access denied, throttling, model not found),
            # EndpointConnectionError (network unreachable), NoCredentialsError, etc.
            # Re-raise so the fallback path handles it the same as a validation failure.
            raise ProviderValidationError(f"{self.name} Bedrock API call failed: {exc}") from exc

        content_blocks: list[dict[str, Any]] = (
            response.get("output", {}).get("message", {}).get("content", [])
        )
        if not content_blocks:
            raise ProviderValidationError(
                f"{self.name} Bedrock response contained no content blocks"
            )
        text: str = content_blocks[0].get("text", "")
        if not text:
            raise ProviderValidationError(
                f"{self.name} Bedrock response first content block has no text"
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

        Everything goes into one user message (rather than a multi-turn
        conversation) so the prompt is model-agnostic — all Bedrock models
        accept a single user turn without needing an alternating assistant reply.

        On a repair attempt the validation error is appended at the end so the
        model sees what was wrong and can correct its output.
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
