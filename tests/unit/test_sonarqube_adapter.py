"""Unit tests for SonarQubeAdapter — queries SonarQube REST API → SecurityInput."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from rrr.collectors.adapters.sonarqube import SonarQubeAdapter, SonarQubeAdapterError
from rrr.collectors.base import CollectorConfig

# ── Helpers ───────────────────────────────────────────────────────────────────

_BASE_URL = "http://sonarqube.internal"
_PROJECT = "com.example:retail-banking"


def _issues_response(issues: list[dict], total: int | None = None) -> bytes:
    """Encode a SonarQube /api/issues/search response body."""
    total_count = total if total is not None else len(issues)
    payload = {"issues": issues, "total": total_count, "p": 1, "ps": 500}
    return json.dumps(payload).encode()


def _mock_urlopen(response_bytes: bytes, status: int = 200):
    """Return a context manager mock that yields a file-like response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_bytes
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _config(tmp_path) -> CollectorConfig:
    return CollectorConfig(release="R1", data_dir=tmp_path)


def _adapter() -> SonarQubeAdapter:
    return SonarQubeAdapter(_BASE_URL, _PROJECT)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_sonarqube_adapter_dimension_is_security():
    assert _adapter().dimension == "security"


def test_sonarqube_adapter_passed_when_no_issues(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    body = _issues_response([])
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = _adapter().collect(_config(tmp_path))
    assert result["sast_status"] == "passed"
    assert result["open_critical_cves"] == 0
    assert result["open_high_cves"] == 0


def test_sonarqube_adapter_failed_when_critical_issues(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    issues = [{"severity": "CRITICAL", "key": "AX01"}]
    body = _issues_response(issues)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = _adapter().collect(_config(tmp_path))
    assert result["sast_status"] == "failed"
    assert result["open_critical_cves"] == 1


def test_sonarqube_adapter_counts_blocker_as_critical(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    issues = [{"severity": "BLOCKER", "key": "AX02"}]
    body = _issues_response(issues)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = _adapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 1


def test_sonarqube_adapter_counts_major_as_high(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    issues = [{"severity": "MAJOR", "key": "AX03"}, {"severity": "MAJOR", "key": "AX04"}]
    body = _issues_response(issues)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = _adapter().collect(_config(tmp_path))
    assert result["open_high_cves"] == 2


def test_sonarqube_adapter_minor_not_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    issues = [{"severity": "MINOR", "key": "AX05"}, {"severity": "INFO", "key": "AX06"}]
    body = _issues_response(issues)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = _adapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 0
    assert result["open_high_cves"] == 0


def test_sonarqube_adapter_pagination(tmp_path, monkeypatch):
    # Two pages of 2 issues each; total=4 so runner must loop.
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    page1_issues = [{"severity": "CRITICAL", "key": "P1A"}, {"severity": "CRITICAL", "key": "P1B"}]
    page2_issues = [{"severity": "MAJOR", "key": "P2A"}, {"severity": "MAJOR", "key": "P2B"}]
    page1 = json.dumps({"issues": page1_issues, "total": 4, "p": 1, "ps": 2}).encode()
    page2 = json.dumps({"issues": page2_issues, "total": 4, "p": 2, "ps": 2}).encode()
    resp1, resp2 = _mock_urlopen(page1), _mock_urlopen(page2)
    with patch("urllib.request.urlopen", side_effect=[resp1, resp2]):
        result = _adapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 2
    assert result["open_high_cves"] == 2


def test_sonarqube_adapter_raises_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("SONARQUBE_TOKEN", raising=False)
    with pytest.raises(SonarQubeAdapterError, match="SONARQUBE_TOKEN"):
        _adapter().collect(_config(tmp_path))


def test_sonarqube_adapter_raises_on_http_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    http_err = urllib.error.HTTPError(
        url="http://x", code=401, msg="Unauthorized", hdrs=None, fp=None
    )
    with (
        patch("urllib.request.urlopen", side_effect=http_err),
        pytest.raises(SonarQubeAdapterError, match="HTTP 401"),
    ):
        _adapter().collect(_config(tmp_path))


def test_sonarqube_adapter_raises_on_connection_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    url_err = urllib.error.URLError("Connection refused")
    with (
        patch("urllib.request.urlopen", side_effect=url_err),
        pytest.raises(SonarQubeAdapterError, match="connect"),
    ):
        _adapter().collect(_config(tmp_path))


def test_sonarqube_adapter_raises_on_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    mock_resp = _mock_urlopen(b"not json{{{")
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(SonarQubeAdapterError, match="non-JSON"),
    ):
        _adapter().collect(_config(tmp_path))


def test_sonarqube_adapter_uses_basic_auth_header(tmp_path, monkeypatch):
    # Verify the Authorization header is correctly encoded (token as username, empty password).
    monkeypatch.setenv("SONARQUBE_TOKEN", "my-secret-token")
    body = _issues_response([])

    captured_headers: list[dict] = []

    def fake_urlopen(req, timeout=None):
        captured_headers.append(dict(req.headers))
        return _mock_urlopen(body)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        _adapter().collect(_config(tmp_path))

    assert captured_headers, "urlopen was never called"
    auth_header = captured_headers[0].get("Authorization", "")
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header[len("Basic "):]).decode()
    # Token is the username; password is empty.
    assert decoded.startswith("my-secret-token:")


def test_sonarqube_adapter_result_validates_against_security_input(tmp_path, monkeypatch):
    from rrr.models.security import SecurityInput

    monkeypatch.setenv("SONARQUBE_TOKEN", "tok")
    issues = [{"severity": "CRITICAL", "key": "K1"}, {"severity": "MAJOR", "key": "K2"}]
    body = _issues_response(issues)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        partial = _adapter().collect(_config(tmp_path))

    model = SecurityInput.model_validate(partial)
    assert model.open_critical_cves == 1
    assert model.open_high_cves == 1
    assert model.sast_status.value == "failed"
