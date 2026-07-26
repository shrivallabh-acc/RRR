"""Tests for LocalLLMProvider: normal, repair, fallback, network-error, allow-list paths."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from rrr.errors import ConfigurationError, ProviderValidationError
from rrr.models.enums import DimensionName
from rrr.models.llm import DimensionReasoning, VerdictSynthesis
from rrr.providers.base import ReasoningRequest
from rrr.providers.local_llm import LocalLLMProvider

_LOCAL_ENDPOINT = "http://127.0.0.1:11434"
_MODEL = "llama3"

_VALID_DIMENSION = DimensionReasoning(
    classification="delivered",
    narrative="All stories completed and tests passing.",
    risk_factors=[],
)
_VALID_VERDICT = VerdictSynthesis(
    rationale="Five dimensions assessed; three strong.",
    remediation=["Deploy to staging first."],
)


def _make_http_response(content: str) -> MagicMock:
    """Return a mock that behaves like urllib's context-manager response."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = json.dumps({"message": {"content": content}}).encode()
    return resp


def _provider(**kwargs: object) -> LocalLLMProvider:
    return LocalLLMProvider(_LOCAL_ENDPOINT, _MODEL, **kwargs)  # type: ignore[arg-type]


# --- allow-list enforcement ----------------------------------------------------------------


def test_init_rejects_non_local_host() -> None:
    with pytest.raises(ConfigurationError, match="allow-list"):
        LocalLLMProvider("http://external.example.com:11434", _MODEL)


def test_init_accepts_localhost() -> None:
    LocalLLMProvider("http://localhost:11434", _MODEL)  # no error


def test_init_accepts_127_0_0_1() -> None:
    LocalLLMProvider(_LOCAL_ENDPOINT, _MODEL)  # no error


def test_init_accepts_custom_allowed_host() -> None:
    LocalLLMProvider("http://192.168.1.10:11434", _MODEL, allowed_hosts=("192.168.1.10",))


# --- provider identity ---------------------------------------------------------------------


def test_name_includes_model() -> None:
    assert _MODEL in _provider().name


# --- normal path ---------------------------------------------------------------------------


def test_reason_returns_validated_model_on_first_try() -> None:
    valid_json = _VALID_DIMENSION.model_dump_json()
    with patch("rrr.providers.local_llm.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_http_response(valid_json)
        result = _provider().reason(
            ReasoningRequest(dimension=DimensionName.SCOPE, summary="95% complete"),
            DimensionReasoning,
        )
    assert isinstance(result, DimensionReasoning)
    assert result.classification == "delivered"
    assert mock_open.call_count == 1


def test_reason_works_for_verdict_synthesis() -> None:
    valid_json = _VALID_VERDICT.model_dump_json()
    with patch("rrr.providers.local_llm.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_http_response(valid_json)
        result = _provider().reason(ReasoningRequest(summary="3/5 green"), VerdictSynthesis)
    assert isinstance(result, VerdictSynthesis)
    assert result.rationale


# --- repair path ---------------------------------------------------------------------------


def test_repair_loop_succeeds_on_second_attempt() -> None:
    """First call returns bad JSON; second (repair) call returns valid JSON."""
    valid_json = _VALID_DIMENSION.model_dump_json()
    responses = [_make_http_response("{}"), _make_http_response(valid_json)]
    with patch("rrr.providers.local_llm.urllib.request.urlopen", side_effect=responses):
        result = _provider().reason(
            ReasoningRequest(dimension=DimensionName.TEST_READINESS),
            DimensionReasoning,
        )
    assert result.classification == "delivered"


def test_repair_call_includes_error_hint_in_message() -> None:
    """Verify the repair hint is present in the second request body."""
    valid_json = _VALID_DIMENSION.model_dump_json()
    captured_bodies: list[dict[str, object]] = []

    def fake_urlopen(req: object, timeout: float | None = None) -> MagicMock:
        import urllib.request as ur

        assert isinstance(req, ur.Request)
        body = json.loads(req.data)  # type: ignore[arg-type]
        captured_bodies.append(body)
        idx = len(captured_bodies) - 1
        return _make_http_response("{}" if idx == 0 else valid_json)

    with patch("rrr.providers.local_llm.urllib.request.urlopen", side_effect=fake_urlopen):
        _provider().reason(ReasoningRequest(), DimensionReasoning)

    assert len(captured_bodies) == 2
    second_messages = captured_bodies[1]["messages"]
    assert isinstance(second_messages, list)
    # The repair message should mention validation failure
    last_msg = second_messages[-1]["content"]
    assert "validation" in last_msg.lower() or "invalid" in last_msg.lower()


# --- fallback path (ProviderValidationError propagates) ------------------------------------


def test_raises_provider_validation_error_after_max_repairs_exhausted() -> None:
    """Both attempts return bad JSON → ProviderValidationError raised (caller degrades)."""
    with patch("rrr.providers.local_llm.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_http_response("{}")
        with pytest.raises(ProviderValidationError):
            _provider().reason(ReasoningRequest(), DimensionReasoning)


def test_no_repair_retries_raises_immediately_on_invalid() -> None:
    with patch("rrr.providers.local_llm.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_http_response("{}")
        with pytest.raises(ProviderValidationError):
            LocalLLMProvider(_LOCAL_ENDPOINT, _MODEL, repair_retries=0).reason(
                ReasoningRequest(), DimensionReasoning
            )
    assert mock_open.call_count == 1


# --- network-error path --------------------------------------------------------------------


def test_url_error_raises_provider_validation_error() -> None:
    with (
        patch(
            "rrr.providers.local_llm.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ),
        pytest.raises(ProviderValidationError, match="cannot reach Ollama"),
    ):
        _provider().reason(ReasoningRequest(), DimensionReasoning)


def test_http_error_raises_provider_validation_error() -> None:
    with (
        patch(
            "rrr.providers.local_llm.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url=_LOCAL_ENDPOINT, code=404, msg="Not Found", hdrs=MagicMock(), fp=None
            ),
        ),
        pytest.raises(ProviderValidationError, match="HTTP 404"),
    ):
        _provider().reason(ReasoningRequest(), DimensionReasoning)


def test_empty_content_raises_provider_validation_error() -> None:
    resp = _make_http_response("")
    resp.read.return_value = json.dumps({"message": {"content": ""}}).encode()
    with (
        patch("rrr.providers.local_llm.urllib.request.urlopen", return_value=resp),
        pytest.raises(ProviderValidationError, match="missing message.content"),
    ):
        _provider().reason(ReasoningRequest(), DimensionReasoning)
