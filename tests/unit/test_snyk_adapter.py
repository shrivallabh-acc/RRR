"""Unit tests for SnykAdapter — shells out to snyk CLI → SecurityInput."""

from __future__ import annotations

import json
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from rrr.collectors.adapters.snyk import (
    _SNYK_EXIT_AUTH_ERROR,
    _SNYK_EXIT_UNSUPPORTED,
    _SNYK_EXIT_VULN_FOUND,
    SnykAdapter,
    SnykAdapterError,
)
from rrr.collectors.base import CollectorConfig

# ── Helpers ───────────────────────────────────────────────────────────────────

def _snyk_json(
    critical: list[str] | None = None,
    high: list[str] | None = None,
    low: list[str] | None = None,
) -> str:
    """Build minimal snyk test --json output with the requested vulnerability ids."""
    vulns = []
    for vid in (critical or []):
        vulns.append({"id": vid, "severity": "critical", "title": f"CVE {vid}"})
    for vid in (high or []):
        vulns.append({"id": vid, "severity": "high", "title": f"CVE {vid}"})
    for vid in (low or []):
        vulns.append({"id": vid, "severity": "low", "title": f"CVE {vid}"})
    return json.dumps({"vulnerabilities": vulns, "ok": len(vulns) == 0})


def _proc(stdout: str = "", returncode: int = 0) -> CompletedProcess:
    return CompletedProcess(args=["snyk"], returncode=returncode, stdout=stdout, stderr="")


def _config(tmp_path) -> CollectorConfig:
    return CollectorConfig(release="R1", data_dir=tmp_path)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_snyk_adapter_dimension_is_security(tmp_path):
    adapter = SnykAdapter()
    assert adapter.dimension == "security"


def test_snyk_adapter_sast_status_is_not_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with patch("subprocess.run", return_value=_proc(_snyk_json())):
        result = SnykAdapter().collect(_config(tmp_path))
    assert result["sast_status"] == "not_run"


def test_snyk_adapter_no_vulns_returns_zero_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with patch("subprocess.run", return_value=_proc(_snyk_json())):
        result = SnykAdapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 0
    assert result["open_high_cves"] == 0


def test_snyk_adapter_counts_critical(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    raw = _snyk_json(critical=["CVE-2024-001", "CVE-2024-002"])
    with patch("subprocess.run", return_value=_proc(raw, returncode=_SNYK_EXIT_VULN_FOUND)):
        result = SnykAdapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 2


def test_snyk_adapter_counts_high(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    raw = _snyk_json(high=["CVE-2024-010", "CVE-2024-011", "CVE-2024-012"])
    with patch("subprocess.run", return_value=_proc(raw, returncode=_SNYK_EXIT_VULN_FOUND)):
        result = SnykAdapter().collect(_config(tmp_path))
    assert result["open_high_cves"] == 3


def test_snyk_adapter_deduplicates_repeated_vuln_ids(tmp_path, monkeypatch):
    # Same CVE via multiple dependency paths must count only once.
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    vulns = [
        {"id": "CVE-2024-999", "severity": "critical"},
        {"id": "CVE-2024-999", "severity": "critical"},  # duplicate path
    ]
    raw = json.dumps({"vulnerabilities": vulns})
    with patch("subprocess.run", return_value=_proc(raw, returncode=_SNYK_EXIT_VULN_FOUND)):
        result = SnykAdapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 1


def test_snyk_adapter_low_severity_not_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    raw = _snyk_json(low=["CVE-2024-LO1", "CVE-2024-LO2"])
    with patch("subprocess.run", return_value=_proc(raw)):
        result = SnykAdapter().collect(_config(tmp_path))
    assert result["open_critical_cves"] == 0
    assert result["open_high_cves"] == 0


def test_snyk_adapter_raises_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    with pytest.raises(SnykAdapterError, match="SNYK_TOKEN"):
        SnykAdapter().collect(_config(tmp_path))


def test_snyk_adapter_raises_on_auth_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "bad-tok")
    with (
        patch("subprocess.run", return_value=_proc("", returncode=_SNYK_EXIT_AUTH_ERROR)),
        pytest.raises(SnykAdapterError, match="authentication failed"),
    ):
        SnykAdapter().collect(_config(tmp_path))


def test_snyk_adapter_raises_on_unsupported_project(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with (
        patch("subprocess.run", return_value=_proc("", returncode=_SNYK_EXIT_UNSUPPORTED)),
        pytest.raises(SnykAdapterError, match="does not support"),
    ):
        SnykAdapter().collect(_config(tmp_path))


def test_snyk_adapter_raises_when_snyk_not_on_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(SnykAdapterError, match="not found"),
    ):
        SnykAdapter().collect(_config(tmp_path))


def test_snyk_adapter_raises_on_empty_output(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with (
        patch("subprocess.run", return_value=_proc("", returncode=0)),
        pytest.raises(SnykAdapterError, match="no output"),
    ):
        SnykAdapter().collect(_config(tmp_path))


def test_snyk_adapter_raises_on_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with (
        patch("subprocess.run", return_value=_proc("not-json{{", returncode=0)),
        pytest.raises(SnykAdapterError, match="parse"),
    ):
        SnykAdapter().collect(_config(tmp_path))


def test_snyk_adapter_result_validates_against_security_input(tmp_path, monkeypatch):
    from rrr.models.security import SecurityInput

    monkeypatch.setenv("SNYK_TOKEN", "tok")
    raw = _snyk_json(critical=["CVE-001"], high=["CVE-002"])
    with patch("subprocess.run", return_value=_proc(raw, returncode=_SNYK_EXIT_VULN_FOUND)):
        partial = SnykAdapter().collect(_config(tmp_path))

    model = SecurityInput.model_validate(partial)
    assert model.open_critical_cves == 1
    assert model.open_high_cves == 1
    assert model.sast_status.value == "not_run"


def test_snyk_adapter_extra_args_passed_to_subprocess(tmp_path, monkeypatch):
    monkeypatch.setenv("SNYK_TOKEN", "tok")
    with patch("subprocess.run", return_value=_proc(_snyk_json())) as mock_run:
        SnykAdapter(snyk_args=["--severity-threshold=high"]).collect(_config(tmp_path))
    cmd = mock_run.call_args[0][0]
    assert "--severity-threshold=high" in cmd
