"""Tests for EnvironmentSourceReader, DependencySourceReader, OperationalSourceReader.

Covers both transport paths: file (JSON + CSV) and localhost API (HTTP GET).
The HTTP path is exercised via unittest.mock so no real server is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rrr.errors import SourceReadError
from rrr.tools.source_reader import (
    DEFAULT_ALLOWED_HOSTS,
    DependencySourceReader,
    EnvironmentSourceReader,
    OperabilitySourceReader,
    OperationalSourceReader,
)

# ---------------------------------------------------------------------------
# Minimal valid payloads
# ---------------------------------------------------------------------------

_ENV_JSON = json.dumps(
    {"components": [{"name": "app-server", "provisioning": "provisioned", "stability": "stable"}]}
)
_DEP_JSON = json.dumps(
    {"dependencies": [{"name": "upstream-api", "completion": "complete", "integration": "passed"}]}
)
_OPS_JSON = json.dumps(
    {
        "schema_version": "1.0.0",
        "deployment_pipeline": "green",
        "rollback_plan": "documented",
        "change_freeze": False,
        "recent_deployment_failures": 0,
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_urlopen(body: str):
    """Return a context-manager mock that yields a readable HTTP-like response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = body.encode("utf-8")
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_resp)
    mock_cm.__exit__ = MagicMock(return_value=False)
    return mock_cm


# ---------------------------------------------------------------------------
# File transport — JSON
# ---------------------------------------------------------------------------


def test_environment_reader_file_json(tmp_path: Path) -> None:
    f = tmp_path / "env.json"
    f.write_text(_ENV_JSON, encoding="utf-8")
    result = EnvironmentSourceReader(path=f).invoke()
    assert result.components[0].name == "app-server"


def test_dependency_reader_file_json(tmp_path: Path) -> None:
    f = tmp_path / "dep.json"
    f.write_text(_DEP_JSON, encoding="utf-8")
    result = DependencySourceReader(path=f).invoke()
    assert result.dependencies[0].name == "upstream-api"


def test_operational_reader_file_json(tmp_path: Path) -> None:
    f = tmp_path / "ops.json"
    f.write_text(_OPS_JSON, encoding="utf-8")
    result = OperationalSourceReader(path=f).invoke()
    # green pipeline → score is not tested here, just that the model loads
    assert result.deployment_pipeline.value == "green"


def test_stub_data_files_are_loadable() -> None:
    """Confirm the committed stub files in data/ are valid against their models."""
    data = Path("data")
    env = EnvironmentSourceReader(path=data / "environment.json").invoke()
    dep = DependencySourceReader(path=data / "dependency.json").invoke()
    ops = OperabilitySourceReader(path=data / "operability.json").invoke()
    assert env.components
    assert dep.dependencies
    assert ops.deployment_pipeline is not None


# ---------------------------------------------------------------------------
# File transport — CSV
# ---------------------------------------------------------------------------


def test_environment_reader_csv(tmp_path: Path) -> None:
    f = tmp_path / "env.csv"
    f.write_text("name,provisioning,stability\ndb,provisioned,stable\n", encoding="utf-8")
    result = EnvironmentSourceReader(path=f).invoke()
    assert result.components[0].name == "db"


def test_dependency_reader_csv(tmp_path: Path) -> None:
    f = tmp_path / "dep.csv"
    f.write_text("name,completion,integration\nsvc,complete,passed\n", encoding="utf-8")
    result = DependencySourceReader(path=f).invoke()
    assert result.dependencies[0].name == "svc"


# ---------------------------------------------------------------------------
# File transport — error cases
# ---------------------------------------------------------------------------


def test_file_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(SourceReadError, match="not found"):
        EnvironmentSourceReader(path=tmp_path / "missing.json").invoke()


def test_invalid_json_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("{bad json", encoding="utf-8")
    with pytest.raises(SourceReadError, match="not valid JSON"):
        EnvironmentSourceReader(path=f).invoke()


def test_json_array_file_raises(tmp_path: Path) -> None:
    # Top-level arrays are not valid — both schemas require a JSON object.
    f = tmp_path / "list.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SourceReadError, match="must be a JSON object"):
        EnvironmentSourceReader(path=f).invoke()


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------


def test_both_path_and_url_raises() -> None:
    with pytest.raises(SourceReadError):
        EnvironmentSourceReader(path="/some/file.json", url="http://127.0.0.1/env")


def test_neither_path_nor_url_raises() -> None:
    with pytest.raises(SourceReadError):
        EnvironmentSourceReader()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# API transport — normal path
# ---------------------------------------------------------------------------


def test_environment_reader_api_normal(tmp_path: Path) -> None:
    url = "http://127.0.0.1:8001/environment"
    with patch("rrr.tools.source_reader.urlopen", return_value=_mock_urlopen(_ENV_JSON)):
        result = EnvironmentSourceReader(url=url).invoke()
    assert result.components[0].name == "app-server"


def test_dependency_reader_api_normal(tmp_path: Path) -> None:
    url = "http://127.0.0.1:8002/dependency"
    with patch("rrr.tools.source_reader.urlopen", return_value=_mock_urlopen(_DEP_JSON)):
        result = DependencySourceReader(url=url).invoke()
    assert result.dependencies[0].name == "upstream-api"


def test_operational_reader_api_normal(tmp_path: Path) -> None:
    url = "http://127.0.0.1:8003/operational"
    with patch("rrr.tools.source_reader.urlopen", return_value=_mock_urlopen(_OPS_JSON)):
        result = OperationalSourceReader(url=url).invoke()
    assert result.deployment_pipeline.value == "green"


# ---------------------------------------------------------------------------
# API transport — allow-list enforcement (reader-level, defense in depth)
# ---------------------------------------------------------------------------


def test_api_host_not_allow_listed_raises() -> None:
    # The reader enforces the allow-list on every invocation, not just at init.
    reader = EnvironmentSourceReader(
        url="http://external.example.com/env",
        # Override allowed_hosts so only the reader-level guard is being tested
        # (the config-level guard is tested in test_config.py).
        allowed_hosts=("127.0.0.1", "localhost"),
    )
    with pytest.raises(SourceReadError, match="not allow-listed"):
        reader.invoke()


def test_localhost_hostname_is_allow_listed() -> None:
    url = "http://localhost:9000/env"
    with patch("rrr.tools.source_reader.urlopen", return_value=_mock_urlopen(_ENV_JSON)):
        result = EnvironmentSourceReader(url=url, allowed_hosts=DEFAULT_ALLOWED_HOSTS).invoke()
    assert result.components


# ---------------------------------------------------------------------------
# API transport — network error cases
# ---------------------------------------------------------------------------


def test_api_connection_error_raises() -> None:
    url = "http://127.0.0.1:8001/environment"
    with (
        patch("rrr.tools.source_reader.urlopen", side_effect=OSError("connection refused")),
        pytest.raises(SourceReadError, match="failed to fetch"),
    ):
        EnvironmentSourceReader(url=url).invoke()


def test_api_malformed_json_raises() -> None:
    # The API path does not wrap JSONDecodeError — it propagates as-is from json.loads().
    url = "http://127.0.0.1:8001/environment"
    with (
        patch("rrr.tools.source_reader.urlopen", return_value=_mock_urlopen("{not json")),
        pytest.raises(json.JSONDecodeError),
    ):
        EnvironmentSourceReader(url=url).invoke()


def test_api_json_array_body_raises() -> None:
    # API returning a JSON array instead of an object → SourceReadError.
    url = "http://127.0.0.1:8001/environment"
    with (
        patch("rrr.tools.source_reader.urlopen", return_value=_mock_urlopen("[1,2,3]")),
        pytest.raises(SourceReadError, match="must be a JSON object"),
    ):
        EnvironmentSourceReader(url=url).invoke()
