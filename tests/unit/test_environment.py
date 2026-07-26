"""Tests for the environment source reader + EnvironmentAssessor (FR-3, NFR-8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rrr.assessors import EnvironmentAssessor
from rrr.errors import SourceReadError
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.environment import EnvironmentInput
from rrr.providers import RuleBasedProvider
from rrr.tools import EnvironmentSourceReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1_ENV = GOLDEN / "g1_clean_release" / "inputs" / "environment.json"


def test_reader_loads_json_fixture() -> None:
    env = EnvironmentSourceReader(path=G1_ENV).invoke()
    assert isinstance(env, EnvironmentInput)
    assert len(env.components) == 5


def test_reader_requires_exactly_one_source() -> None:
    with pytest.raises(SourceReadError, match="exactly one"):
        EnvironmentSourceReader()
    with pytest.raises(SourceReadError, match="exactly one"):
        EnvironmentSourceReader(path="x.json", url="http://127.0.0.1/env")


def test_reader_rejects_non_allowlisted_api_host() -> None:
    reader = EnvironmentSourceReader(url="http://evil.example.com/env")
    with pytest.raises(SourceReadError, match="not allow-listed"):
        reader.invoke()


def test_reader_parses_csv(tmp_path: Path) -> None:
    csv_file = tmp_path / "environment.csv"
    csv_file.write_text(
        "name,provisioning,stability,notes\n"
        "API,validated,stable,\n"
        "DB,configured,degraded,awaiting sign-off\n",
        encoding="utf-8",
    )
    env = EnvironmentSourceReader(path=csv_file).invoke()
    assert {c.name for c in env.components} == {"API", "DB"}


def test_missing_file_raises() -> None:
    with pytest.raises(SourceReadError, match="not found"):
        EnvironmentSourceReader(path="does/not/exist.json").invoke()


def _assessor(path: Path) -> EnvironmentAssessor:
    return EnvironmentAssessor(
        ToolRunner(), RuleBasedProvider(), EnvironmentSourceReader(path=path)
    )


def test_g1_environment_score_matches_oracle() -> None:
    result = _assessor(G1_ENV).assess()
    assert result.dimension is DimensionName.ENVIRONMENT and result.available is True
    assert abs(result.score - 0.950) < 0.03  # matches g1 ideal.json (one 'configured' of five)
    assert result.classification == "ready"  # all stable, none missing
    assert result.confidence == 1.0


def test_stability_drives_risk_not_score(tmp_path: Path) -> None:
    """A validated-but-down component still scores 1.0 but raises a critical risk (FR-3)."""
    src = tmp_path / "environment.json"
    src.write_text(
        '{"components": ['
        '{"name": "API", "provisioning": "validated", "stability": "down"},'
        '{"name": "DB", "provisioning": "validated", "stability": "stable"}]}',
        encoding="utf-8",
    )
    result = _assessor(src).assess()
    assert result.score == 1.0  # provisioning is perfect…
    assert result.classification == "not_ready"  # …but a component is down
    crit = [r for r in result.risk_factors if r.severity is RiskSeverity.CRITICAL]
    assert len(crit) == 1 and "down" in crit[0].description


def test_missing_provisioning_raises_major_risk(tmp_path: Path) -> None:
    src = tmp_path / "environment.json"
    src.write_text(
        '{"components": [{"name": "Cache", "provisioning": "missing", "stability": "stable"}]}',
        encoding="utf-8",
    )
    result = _assessor(src).assess()
    assert result.score == 0.0 and result.classification == "at_risk"
    assert any(
        r.severity is RiskSeverity.MAJOR and "missing" in r.description for r in result.risk_factors
    )
