"""Tests for BedrockProvider (ADR-0019).

boto3 is mocked throughout — no real AWS credentials or network calls.
Covers: normal path, repair path, API error fallback, empty-response fallback,
missing-boto3 error, missing-config error, and pipeline wiring.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from rrr.config.schema import BedrockConfig, ProviderConfig, ProviderType
from rrr.errors import ConfigurationError, ProviderValidationError
from rrr.models.llm import DimensionReasoning
from rrr.providers.base import ReasoningRequest

if TYPE_CHECKING:
    from rrr.providers.bedrock import BedrockProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bedrock_response(text: str) -> dict:
    """Build a minimal Bedrock Converse API response dict."""
    return {"output": {"message": {"content": [{"text": text}]}}}


_VALID_JSON = json.dumps(
    {"classification": "partially_delivered", "narrative": "Good progress.", "risk_factors": []}
)
_INVALID_JSON = '{"classification": "oops"'  # missing closing brace


def _make_provider(mock_client: MagicMock) -> BedrockProvider:
    """Create a BedrockProvider with a pre-wired mock boto3 client."""
    from rrr.providers.bedrock import BedrockProvider

    with patch("boto3.client", return_value=mock_client):
        return BedrockProvider("anthropic.claude-3-5-sonnet-20241022-v2:0")


# ---------------------------------------------------------------------------
# Normal path
# ---------------------------------------------------------------------------


def test_reason_returns_validated_model_on_normal_response() -> None:
    mock_client = MagicMock()
    mock_client.converse.return_value = _make_bedrock_response(_VALID_JSON)
    provider = _make_provider(mock_client)

    result = provider.reason(ReasoningRequest(summary="test"), DimensionReasoning)

    assert result.classification == "partially_delivered"
    assert result.narrative == "Good progress."
    assert result.risk_factors == []
    mock_client.converse.assert_called_once()


def test_provider_name_includes_model_id() -> None:
    mock_client = MagicMock()
    provider = _make_provider(mock_client)

    assert "BedrockProvider" in provider.name
    assert "anthropic.claude-3-5-sonnet-20241022-v2:0" in provider.name


# ---------------------------------------------------------------------------
# Repair path
# ---------------------------------------------------------------------------


def test_reason_repairs_on_first_invalid_response() -> None:
    mock_client = MagicMock()
    # First call returns invalid JSON; second call (repair) returns valid JSON.
    mock_client.converse.side_effect = [
        _make_bedrock_response(_INVALID_JSON),
        _make_bedrock_response(_VALID_JSON),
    ]
    provider = _make_provider(mock_client)

    result = provider.reason(ReasoningRequest(summary="repair test"), DimensionReasoning)

    assert result.classification == "partially_delivered"
    assert mock_client.converse.call_count == 2


def test_reason_raises_provider_error_after_exhausting_retries() -> None:
    mock_client = MagicMock()
    # Both calls return invalid JSON — exhausts the 1 repair retry.
    mock_client.converse.return_value = _make_bedrock_response(_INVALID_JSON)
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError):
        provider.reason(ReasoningRequest(summary="no fix"), DimensionReasoning)

    assert mock_client.converse.call_count == 2


def test_repair_call_includes_hint_in_message() -> None:
    """The second (repair) call must include the validation error in the prompt."""
    mock_client = MagicMock()
    mock_client.converse.side_effect = [
        _make_bedrock_response(_INVALID_JSON),
        _make_bedrock_response(_VALID_JSON),
    ]
    provider = _make_provider(mock_client)
    provider.reason(ReasoningRequest(summary="hint check"), DimensionReasoning)

    # The second call's user message should mention validation failure.
    second_call_message = mock_client.converse.call_args_list[1]
    user_text = second_call_message.kwargs["messages"][0]["content"][0]["text"]
    assert "failed JSON schema validation" in user_text


# ---------------------------------------------------------------------------
# Fallback — API errors
# ---------------------------------------------------------------------------


def test_reason_raises_provider_error_on_client_error() -> None:
    """boto3 ClientError (access denied, throttling, etc.) → ProviderValidationError."""
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "Converse",
    )
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="Bedrock API call failed"):
        provider.reason(ReasoningRequest(summary="access denied"), DimensionReasoning)


def test_reason_raises_provider_error_on_endpoint_connection_error() -> None:
    """Network unreachable → ProviderValidationError."""
    from botocore.exceptions import EndpointConnectionError

    mock_client = MagicMock()
    mock_client.converse.side_effect = EndpointConnectionError(endpoint_url="https://bedrock.aws")
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="Bedrock API call failed"):
        provider.reason(ReasoningRequest(summary="network error"), DimensionReasoning)


def test_reason_raises_provider_error_on_empty_content_blocks() -> None:
    """Response with no content blocks → ProviderValidationError."""
    mock_client = MagicMock()
    mock_client.converse.return_value = {"output": {"message": {"content": []}}}
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="no content blocks"):
        provider.reason(ReasoningRequest(summary="empty"), DimensionReasoning)


def test_reason_raises_provider_error_on_blank_text() -> None:
    """Content block present but text is empty string → ProviderValidationError."""
    mock_client = MagicMock()
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": ""}]}}}
    provider = _make_provider(mock_client)

    with pytest.raises(ProviderValidationError, match="no text"):
        provider.reason(ReasoningRequest(summary="blank"), DimensionReasoning)


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


def test_init_raises_configuration_error_if_boto3_missing() -> None:
    """Missing boto3 package → ConfigurationError (not ImportError).

    Setting sys.modules['boto3'] = None causes Python's import machinery to raise
    ImportError when the provider tries ``import boto3`` — simulating the package
    not being installed without actually uninstalling it.
    """
    import sys
    from unittest.mock import patch

    with patch.dict(sys.modules, {"boto3": None}):  # type: ignore[dict-item]
        from rrr.providers.bedrock import BedrockProvider

        with pytest.raises(ConfigurationError, match="boto3 is not installed"):
            BedrockProvider("some-model")


# ---------------------------------------------------------------------------
# Pipeline wiring
# ---------------------------------------------------------------------------


def test_build_provider_returns_bedrock_instance() -> None:
    """pipeline.build_provider() with type=bedrock returns a BedrockProvider."""
    from rrr.pipeline import build_provider
    from rrr.providers.bedrock import BedrockProvider

    provider_cfg = ProviderConfig(
        type=ProviderType.BEDROCK,
        bedrock=BedrockConfig(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            region="us-east-1",
        ),
    )

    mock_config = MagicMock()
    mock_config.provider = provider_cfg

    mock_client = MagicMock()
    with patch("boto3.client", return_value=mock_client):
        result = build_provider(mock_config)

    assert isinstance(result, BedrockProvider)
    assert "anthropic.claude-3-5-sonnet-20241022-v2:0" in result.name


def test_build_provider_raises_when_bedrock_block_missing() -> None:
    """Type=bedrock but no [provider.bedrock] block → ConfigurationError."""
    from rrr.pipeline import build_provider

    provider_cfg = ProviderConfig(type=ProviderType.BEDROCK, bedrock=None)
    mock_config = MagicMock()
    mock_config.provider = provider_cfg

    with pytest.raises(ConfigurationError, match="provider.bedrock.*config block"):
        build_provider(mock_config)
