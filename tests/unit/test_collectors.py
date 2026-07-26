"""Tests for the collectors package — CollectorRunner, CollectorRegistry, InteractiveCollector, CLI.

Coverage:
  CollectorRunner.status()    — FRESH / STALE / MISSING detection, staleness threshold
  CollectorRunner.run()       — validation + write + captured_at stamp
  CollectorRegistry           — model_for(), is_registered(), KeyError on unknown
  InteractiveCollector        — field prompting via Click mocks, _load_existing()
  rrr-collect CLI             — --status exit codes, --dimension, missing --release
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from rrr.collectors._cli import cli
from rrr.collectors.base import BaseCollector, CollectorConfig
from rrr.collectors.interactive import InteractiveCollector, _load_existing
from rrr.collectors.registry import CollectorRegistry
from rrr.collectors.runner import CollectorRunner, CollectorStatus
from rrr.models.operability import OperabilityInput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _fresh_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _old_timestamp(days: int = 10) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# CollectorRunner.status()
# ---------------------------------------------------------------------------

def test_status_missing_when_no_file(tmp_path):
    runner = CollectorRunner()
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.MISSING
    assert reports[0].file_path is None
    assert reports[0].age_days is None


def test_status_fresh_within_threshold(tmp_path):
    _write_json(tmp_path / "operability.json", {"captured_at": _fresh_timestamp()})
    runner = CollectorRunner(staleness_days=7)
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.FRESH
    assert reports[0].age_days is not None and reports[0].age_days < 1


def test_status_stale_beyond_threshold(tmp_path):
    _write_json(tmp_path / "operability.json", {"captured_at": _old_timestamp(days=10)})
    runner = CollectorRunner(staleness_days=7)
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.STALE
    assert reports[0].age_days > 7


def test_status_stale_when_no_timestamp(tmp_path):
    _write_json(tmp_path / "operability.json", {"schema_version": "1.0.0"})
    runner = CollectorRunner()
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.STALE


def test_status_missing_on_invalid_json(tmp_path):
    (tmp_path / "operability.json").write_text("{not valid json", encoding="utf-8")
    runner = CollectorRunner()
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.MISSING


def test_status_multiple_dimensions_ordered(tmp_path):
    _write_json(tmp_path / "operability.json", {"captured_at": _fresh_timestamp()})
    # rollback.json absent
    runner = CollectorRunner()
    reports = runner.status(["operability", "rollback"], tmp_path)
    assert reports[0].dimension == "operability"
    assert reports[0].status == CollectorStatus.FRESH
    assert reports[1].dimension == "rollback"
    assert reports[1].status == CollectorStatus.MISSING


def test_status_just_within_threshold_is_fresh(tmp_path):
    # 6 days old with a 7-day threshold → clearly FRESH.
    _write_json(tmp_path / "operability.json", {"captured_at": _old_timestamp(days=6)})
    runner = CollectorRunner(staleness_days=7)
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.FRESH


def test_status_just_beyond_threshold_is_stale(tmp_path):
    # 8 days old with a 7-day threshold → clearly STALE.
    _write_json(tmp_path / "operability.json", {"captured_at": _old_timestamp(days=8)})
    runner = CollectorRunner(staleness_days=7)
    reports = runner.status(["operability"], tmp_path)
    assert reports[0].status == CollectorStatus.STALE


# ---------------------------------------------------------------------------
# CollectorRunner.run()
# ---------------------------------------------------------------------------

class _FixedCollector(BaseCollector):
    """Stub collector that returns a predetermined dict."""

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def dimension(self) -> str:
        return "operability"

    def collect(self, config: CollectorConfig) -> dict:
        return dict(self._data)


def test_run_writes_json_file(tmp_path):
    data = {"deployment_pipeline": "green", "runbook_complete": True}
    collector = _FixedCollector(data)
    config = CollectorConfig(release="test-release", data_dir=tmp_path)
    runner = CollectorRunner()

    result = runner.run("operability", collector, config, OperabilityInput)

    written = json.loads((tmp_path / "operability.json").read_text(encoding="utf-8"))
    assert written["deployment_pipeline"] == "green"
    assert result.dimension == "operability"
    assert result.collected_at != ""


def test_run_stamps_captured_at_when_absent(tmp_path):
    collector = _FixedCollector({"deployment_pipeline": "green"})
    config = CollectorConfig(release="rel", data_dir=tmp_path)
    runner = CollectorRunner()

    runner.run("operability", collector, config, OperabilityInput)

    written = json.loads((tmp_path / "operability.json").read_text(encoding="utf-8"))
    assert written["captured_at"] is not None


def test_run_preserves_existing_captured_at(tmp_path):
    ts = "2026-07-01T00:00:00.000Z"
    collector = _FixedCollector({"captured_at": ts, "deployment_pipeline": "green"})
    config = CollectorConfig(release="rel", data_dir=tmp_path)
    runner = CollectorRunner()

    result = runner.run("operability", collector, config, OperabilityInput)

    assert result.collected_at == ts


def test_run_returns_correct_dimension(tmp_path):
    collector = _FixedCollector({"deployment_pipeline": "green"})
    config = CollectorConfig(release="my-release", data_dir=tmp_path)
    runner = CollectorRunner()

    result = runner.run("operability", collector, config, OperabilityInput)

    assert result.dimension == "operability"
    # release field in the file comes from the collector, not the runner.
    written = json.loads((tmp_path / "operability.json").read_text(encoding="utf-8"))
    assert written["deployment_pipeline"] == "green"


# ---------------------------------------------------------------------------
# CollectorRegistry
# ---------------------------------------------------------------------------

def test_registry_model_for_known_dimension():
    reg = CollectorRegistry()
    model = reg.model_for("operability")
    assert model is OperabilityInput


def test_registry_model_for_unknown_raises():
    reg = CollectorRegistry()
    with pytest.raises(KeyError, match="not in the collector registry"):
        reg.model_for("nonexistent_dimension")


def test_registry_is_registered_true():
    reg = CollectorRegistry()
    assert reg.is_registered("accessibility") is True


def test_registry_is_registered_false():
    reg = CollectorRegistry()
    assert reg.is_registered("scope") is False  # brain-backed, not in supplementary registry


def test_registry_dimensions_returns_all():
    reg = CollectorRegistry()
    dims = reg.dimensions()
    assert "operability" in dims
    assert "architecture_drift" in dims
    assert len(dims) == 14  # 14 supplementary dimensions


def test_registry_custom_models():
    reg = CollectorRegistry({"test_dim": OperabilityInput})
    assert reg.model_for("test_dim") is OperabilityInput
    assert reg.dimensions() == ["test_dim"]


# ---------------------------------------------------------------------------
# InteractiveCollector._load_existing()
# ---------------------------------------------------------------------------

def test_load_existing_returns_dict_when_valid(tmp_path):
    data = {"deployment_pipeline": "green"}
    _write_json(tmp_path / "operability.json", data)
    result = _load_existing(tmp_path / "operability.json")
    assert result == data


def test_load_existing_returns_empty_when_missing(tmp_path):
    result = _load_existing(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_existing_returns_empty_on_invalid_json(tmp_path):
    (tmp_path / "bad.json").write_text("{invalid", encoding="utf-8")
    result = _load_existing(tmp_path / "bad.json")
    assert result == {}


# ---------------------------------------------------------------------------
# InteractiveCollector.collect() — Click prompts mocked
# ---------------------------------------------------------------------------

def test_interactive_collector_fills_auto_fields(tmp_path):
    collector = InteractiveCollector("operability", OperabilityInput)
    config = CollectorConfig(release="rel-001", data_dir=tmp_path)

    # Mock all Click interactions to return deterministic values.
    with patch("rrr.collectors.interactive.click.prompt", return_value="green"), \
         patch("rrr.collectors.interactive.click.confirm", return_value=True), \
         patch("rrr.collectors.interactive.click.echo"):
        result = collector.collect(config)

    assert result["schema_version"] == "1.0.0"
    assert result["release"] == "rel-001"
    assert result["captured_at"] is not None


def test_interactive_collector_uses_existing_defaults(tmp_path):
    existing = {"deployment_pipeline": "green", "runbook_complete": True}
    _write_json(tmp_path / "operability.json", existing)

    collector = InteractiveCollector("operability", OperabilityInput)
    config = CollectorConfig(release="rel-002", data_dir=tmp_path, skip_optional=True)

    prompted_calls = []

    def _mock_prompt(label, **kwargs):
        prompted_calls.append(label)
        return kwargs.get("default", "green")

    with patch("rrr.collectors.interactive.click.prompt", side_effect=_mock_prompt), \
         patch("rrr.collectors.interactive.click.confirm", return_value=True), \
         patch("rrr.collectors.interactive.click.echo"):
        result = collector.collect(config)

    # deployment_pipeline should use the existing file's "green" as default.
    assert result["deployment_pipeline"] == "green"


def test_interactive_collector_dimension_property():
    collector = InteractiveCollector("operability", OperabilityInput)
    assert collector.dimension == "operability"


# ---------------------------------------------------------------------------
# rrr-collect CLI — using Click test runner
# ---------------------------------------------------------------------------

def test_cli_status_exits_two_when_stale(tmp_path):
    # No files → all MISSING → exit 2.
    runner_cli = CliRunner()
    result = runner_cli.invoke(cli, ["--status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "MISSING" in result.output


def test_cli_status_exits_zero_when_all_fresh(tmp_path):
    registry = CollectorRegistry()
    for dim in registry.dimensions():
        _write_json(tmp_path / f"{dim}.json", {"captured_at": _fresh_timestamp()})

    runner_cli = CliRunner()
    result = runner_cli.invoke(cli, ["--status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "FRESH" in result.output


def test_cli_missing_release_for_dimension_exits_one(tmp_path):
    runner_cli = CliRunner()
    result = runner_cli.invoke(cli, ["--dimension", "operability", "--data-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "--release" in result.output


def test_cli_unknown_dimension_exits_one(tmp_path):
    runner_cli = CliRunner()
    result = runner_cli.invoke(
        cli, ["--release", "r1", "--dimension", "not_a_real_dim", "--data-dir", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "not registered" in result.output


def test_cli_dimension_skips_fresh_without_refresh(tmp_path):
    _write_json(tmp_path / "operability.json", {"captured_at": _fresh_timestamp()})

    runner_cli = CliRunner()
    result = runner_cli.invoke(
        cli, ["--release", "r1", "--dimension", "operability", "--data-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "already FRESH" in result.output


def test_cli_help_displays_options():
    runner_cli = CliRunner()
    result = runner_cli.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--status" in result.output
    assert "--dimension" in result.output
    assert "--all" in result.output


def test_cli_no_mode_exits_one(tmp_path):
    runner_cli = CliRunner()
    # --release given but no mode flag → error.
    result = runner_cli.invoke(cli, ["--release", "r1", "--data-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_cli_status_hotfix_tier_excludes_accessibility(tmp_path):
    registry = CollectorRegistry()
    # Fill all with fresh timestamps.
    for dim in registry.dimensions():
        _write_json(tmp_path / f"{dim}.json", {"captured_at": _fresh_timestamp()})

    runner_cli = CliRunner()
    result = runner_cli.invoke(
        cli, ["--status", "--tier", "hotfix", "--data-dir", str(tmp_path)]
    )
    # accessibility is excluded for hotfix — should not appear in output.
    assert "accessibility" not in result.output
