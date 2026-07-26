"""LLM provider abstraction — where judgment (not scoring) lives (ADR-0006, ADR-0009).

``LLMProvider.reason(request, response_model)`` returns schema-validated structured
output. The numeric score and verdict label stay deterministic regardless of
provider (ADR-0009 #3).

Implementations:
- ``RuleBasedProvider``  — default, no model, fully offline; also the guardrail fallback.
- ``LocalLLMProvider``   — Ollama / llama.cpp on 127.0.0.1 (opt-in, Phase 1).
- ``MockLLMProvider``    — fixture-backed demo provider, no model required (opt-in, Phase 1).
- ``BedrockProvider``    — Amazon Bedrock Converse API, Phase 2 (ADR-0019, requires boto3).
- ``ClaudeProvider``     — Anthropic Messages API, Phase 2 external scale-out
  (ADR-0006, requires anthropic).

:func:`parse_with_repair` is the shared structured-output repair loop (ADR-0009 #2).
"""

from __future__ import annotations

from rrr.providers.base import LLMProvider, ReasoningModel, ReasoningRequest
from rrr.providers.guardrails import parse_with_repair
from rrr.providers.mock_llm import MockLLMProvider
from rrr.providers.rule_based import RuleBasedProvider

__all__ = [
    "LLMProvider",
    "ReasoningRequest",
    "ReasoningModel",
    "RuleBasedProvider",
    "MockLLMProvider",
    "parse_with_repair",
]
