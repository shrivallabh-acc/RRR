"""Tests for ClaudeProvider (ADR-0006, Phase 2).

The anthropic SDK is mocked throughout — no real API key or network calls needed.
Covers: normal path, repair path, exhausted retries, API error fallback, empty
content blocks, blank text, missing SDK, missing API key, and pipeline wiring.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from rrr.config.schema import ClaudeConfig, ProviderConfig, ProviderType
from rrr.errors import ConfigurationError, ProviderValidationError
from rrr.models.llm import DimensionReasoning
from rrr.providers.base import ReasoningRequest

if TYPE_CHECKING:
    from rrr.providers.claude import ClaudeProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_anthropic_response(text: str) -> MagicMock:
    """Build a minimal Anthropic Messages API response object."""
    content_block = MagicMock()
    content_block.text = text
    message = MagicMock()
    message.content = [content_block]
    return message


_VALID_JSON = json.dumps(
    {"classification": "partially_delivered", "narrative": "Good progress.", "risk_factors": []}
)
_INVALID_JSON = '{"classification": "oops"'  # missing closing brace


def _make_provider(mock_client: MagicMock) -> ClaudeProvider:
    """Create a ClaudeProvider with a pre-wired mock Anthropic client."""
    from rrr.providers.claude import ClaudeProvider

    with patch("anthropic.Anthropic", return_value=mock_client):
        return ClaudeProvider("claude-sonnet-4-6", api_key="test-key-sk-ant-123")


# ---------------------------------------------------------------------------
# Normal path
# ---------------------------------------------------------------------------


def test_reason_returns_validated_model_on_normal_response() -> None:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(_VALID_JSON)
    provider = _make_provider(mock_client)

    result = provider.reason(ReasoningRequest(summary="test"), DimensionReasoning)

    assert result.classification == "partially_delivered"
    assert result.narrative == "Good progress."
    assert result.risk_factors == []
    mock_client.messages.create.assert_called_once()


def test_provider_name_includes_model() -> None:
    mock_client = MagicMock()
    provider = _make_provider(mock_client)

    assert "ClaudeProvider" in provider.name
    assert "claude-sonnet-4-6" in provider.name


def test_reason_passes_system_prompt_and_user_message() -> None:
    """messages.create() must receive a non-empty system prompt and user turn."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(_VALID_JSON)
    provider = _make_provider(mock_client)

    provider.reason(ReasoningRequest(summary="check call shape"), DimensionReasoning)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"]  # non-empty system prompt
    assert call_kwargs["messages"][0]["role"] == "user"
    assert call_kwargs["messages"][0]["content"]  # non-empty user content


# ---------------------------------------------------------------------------
# Repair path
# ---------------------------------------------------------------------------


def test_reason_repairs_on_first_invalid_response() -> None:
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_anthropic_response(_INVALID_JSON),
        _make_anthropic_response(_VALID_JSON),
    ]
    provider = _make_provider(mock_client)

    result = provider.reason(ReasoningRequest(summary="repair test"), DimensionReasoning)

    assert result.classification == "partially_delivered"
    assert mock_client.messages.create.call_count == 2


def test_reason_raises_provider_error_after_exhausting_retries() -> None:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(_INVALID_JSON)
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError):
        provider.reason(ReasoningRequest(summary="no fix"), DimensionReasoning)

    assert mock_client.messages.create.call_count == 2


def test_repair_call_includes_validation_hint_in_user_message() -> None:
    """The second (repair) call's user content must mention the validation failure."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_anthropic_response(_INVALID_JSON),
        _make_anthropic_response(_VALID_JSON),
    ]
    provider = _make_provider(mock_client)
    provider.reason(ReasoningRequest(summary="hint check"), DimensionReasoning)

    second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    user_content = second_call_kwargs["messages"][0]["content"]
    assert "failed JSON schema validation" in user_content


# ---------------------------------------------------------------------------
# Fallback — API errors
# ---------------------------------------------------------------------------


def test_reason_raises_provider_error_on_api_exception() -> None:
    """Any exception from messages.create() → ProviderValidationError."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("network unreachable")
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="Anthropic API call failed"):
        provider.reason(ReasoningRequest(summary="api error"), DimensionReasoning)


def test_reason_raises_provider_error_on_empty_content() -> None:
    """Response with no content blocks → ProviderValidationError."""
    mock_client = MagicMock()
    empty_msg = MagicMock()
    empty_msg.content = []
    mock_client.messages.create.return_value = empty_msg
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="no content blocks"):
        provider.reason(ReasoningRequest(summary="empty content"), DimensionReasoning)


def test_reason_raises_provider_error_on_blank_text() -> None:
    """Content block present but text is empty string → ProviderValidationError."""
    mock_client = MagicMock()
    blank_block = MagicMock()
    blank_block.text = ""
    blank_msg = MagicMock()
    blank_msg.content = [blank_block]
    mock_client.messages.create.return_value = blank_msg
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="no text"):
        provider.reason(ReasoningRequest(summary="blank text"), DimensionReasoning)


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


def test_init_raises_configuration_error_if_anthropic_missing() -> None:
    """Missing anthropic package → ConfigurationError (not ImportError).

    Setting sys.modules['anthropic'] = None causes Python's import machinery to
    raise ImportError when the provider tries ``import anthropic`` — simulating
    the package not being installed without actually uninstalling it.
    """
    with patch.dict(sys.modules, {"anthropic": None}):  # type: ignore[dict-item]
        from rrr.providers.claude import ClaudeProvider

        with pytest.raises(ConfigurationError, match="anthropic package is not installed"):
            ClaudeProvider("claude-sonnet-4-6", api_key="test-key")


def test_init_raises_configuration_error_if_no_api_key() -> None:
    """No api_key argument and no ANTHROPIC_API_KEY env var → ConfigurationError."""
    import os

    os.environ.pop("ANTHROPIC_API_KEY", None)
    mock_client = MagicMock()
    with (
        patch("anthropic.Anthropic", return_value=mock_client),
        patch.dict("os.environ", {}, clear=False),
    ):
        from rrr.providers.claude import ClaudeProvider

        with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
            ClaudeProvider("claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Pipeline wiring
# ---------------------------------------------------------------------------


def test_build_provider_returns_claude_instance() -> None:
    """pipeline.build_provider() with type=claude returns a ClaudeProvider."""
    from rrr.pipeline import build_provider
    from rrr.providers.claude import ClaudeProvider

    provider_cfg = ProviderConfig(
        type=ProviderType.CLAUDE,
        claude=ClaudeConfig(model="claude-sonnet-4-6"),
    )
    mock_config = MagicMock()
    mock_config.provider = provider_cfg

    mock_client = MagicMock()
    with (
        patch("anthropic.Anthropic", return_value=mock_client),
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key-sk-ant"}),
    ):
        result = build_provider(mock_config)

    assert isinstance(result, ClaudeProvider)
    assert "claude-sonnet-4-6" in result.name


def test_build_provider_raises_when_claude_block_missing() -> None:
    """Type=claude but no [provider.claude] block → ConfigurationError."""
    from rrr.pipeline import build_provider

    provider_cfg = ProviderConfig(type=ProviderType.CLAUDE, claude=None)
    mock_config = MagicMock()
    mock_config.provider = provider_cfg

    with pytest.raises(ConfigurationError, match="provider.claude.*config block"):
        build_provider(mock_config)
