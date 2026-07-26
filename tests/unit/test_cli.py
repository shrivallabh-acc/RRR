"""Tests for the composition root (pipeline.assess) and the Click CLI (FR-16/17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rrr.cli import main
from rrr.config import ConfigLoader
from rrr.errors import ConfigurationError
from rrr.models.enums import Verdict
from rrr.pipeline import assess, build_provider

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
VS = "Retirement-Services"


def _overrides(sample: str) -> dict:
    inp = GOLDEN / sample / "inputs"
    return {
        "sources": {
            "brain": {"dir": str(inp / "brain"), "value_stream": VS},
            "environment": {"type": "file", "path": str(inp / "environment.json")},
            "dependency": {"type": "file", "path": str(inp / "dependency.json")},
            "operability": {"type": "file", "path": str(inp / "operability.json")},
        }
    }


def _config_file(tmp_path: Path, sample: str) -> Path:
    inp = GOLDEN / sample / "inputs"
    db = (tmp_path / "rrr.sqlite").as_posix()
    text = (
        "sources:\n"
        f'  brain: {{ dir: "{(inp / "brain").as_posix()}", value_stream: "{VS}" }}\n'
        f'  environment: {{ type: file, path: "{(inp / "environment.json").as_posix()}" }}\n'
        f'  dependency: {{ type: file, path: "{(inp / "dependency.json").as_posix()}" }}\n'
        f'  operability: {{ type: file, path: "{(inp / "operability.json").as_posix()}" }}\n'
        "memory:\n"
        f'  sqlite_path: "{db}"\n'
    )
    path = tmp_path / "cfg.yaml"
    path.write_text(text, encoding="utf-8")
    return path


# --- pipeline (composition root) --------------------------------------------------------------


def test_pipeline_g1_is_go() -> None:
    out = assess(
        ConfigLoader.load(overrides=_overrides("g1_clean_release")),
        release="Launch 36 - Unified Onboarding",
    )
    assert out.verdict is Verdict.GO
    assert len(out.dimensions) == 6


def test_pipeline_g2_is_no_go() -> None:
    out = assess(
        ConfigLoader.load(overrides=_overrides("g2_failing_tests")),
        release="Launch 37 - Payments Hub",
    )
    assert out.verdict is Verdict.NO_GO


def test_build_provider_rejects_claude_without_config_block() -> None:
    """type=claude but no [provider.claude] block → ConfigurationError about missing block."""
    cfg = ConfigLoader.load(overrides={"provider": {"type": "claude"}})
    with pytest.raises(ConfigurationError, match=r"provider\.claude.*config block"):
        build_provider(cfg)


# --- CLI --------------------------------------------------------------------------------------


def test_cli_go_prints_verdict_and_exits_zero(tmp_path: Path) -> None:
    cfg = _config_file(tmp_path, "g1_clean_release")
    res = CliRunner().invoke(
        main, ["--release", "Launch 36 - Unified Onboarding", "--config", str(cfg)]
    )
    assert res.exit_code == 0
    assert "VERDICT: GO" in res.output and "SCORE: 97" in res.output


def test_cli_no_go_exits_one(tmp_path: Path) -> None:
    cfg = _config_file(tmp_path, "g2_failing_tests")
    res = CliRunner().invoke(main, ["--release", "Launch 37 - Payments Hub", "--config", str(cfg)])
    assert res.exit_code == 1 and "VERDICT: NO_GO" in res.output


def test_cli_verbose_emits_json(tmp_path: Path) -> None:
    cfg = _config_file(tmp_path, "g1_clean_release")
    res = CliRunner().invoke(
        main, ["--release", "Launch 36 - Unified Onboarding", "--config", str(cfg), "--verbose"]
    )
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["schema_version"] == "1.0.0" and data["verdict"] == "GO"


def test_cli_unknown_release_is_incomplete_exit_three(tmp_path: Path) -> None:
    cfg = _config_file(tmp_path, "g1_clean_release")
    res = CliRunner().invoke(main, ["--release", "Launch 99 - Ghost", "--config", str(cfg)])
    # 3 brain-sourced dimensions go unavailable -> fewer than minimum_assessors -> INCOMPLETE
    assert res.exit_code == 3 and "VERDICT: INCOMPLETE" in res.output


def test_cli_dry_run_returns_verdict_without_persisting(tmp_path: Path) -> None:
    cfg = _config_file(tmp_path, "g1_clean_release")
    res = CliRunner().invoke(
        main,
        ["--release", "Launch 36 - Unified Onboarding", "--config", str(cfg), "--dry-run"],
    )
    assert res.exit_code == 0
    assert "VERDICT: GO" in res.output
    assert "DRY RUN" in res.output
    # run_and_record() is bypassed — no SQLite file should have been created.
    assert not (tmp_path / "rrr.sqlite").exists()


def test_cli_missing_config_file_errors_exit_three(tmp_path: Path) -> None:
    res = CliRunner().invoke(main, ["--release", "X", "--config", str(tmp_path / "nope.yaml")])
    assert res.exit_code == 3 and "ERROR" in res.output
