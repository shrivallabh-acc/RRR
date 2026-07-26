"""Smoke tests for the M1 Pydantic model layer.

Validates that the input contracts parse the real golden fixtures and that the
output value objects enforce their invariants and serialise as expected.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from rrr.models import (
    AssessmentOutputModel,
    AuditTrail,
    BrainHistory,
    DependencyInput,
    DimensionName,
    DimensionResult,
    EnvironmentInput,
    Verdict,
    iso_millis,
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "g1_clean_release" / "inputs"
BRAIN = GOLDEN / "brain" / "Retirement-Services-history.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_brain_history_parses_real_fixture() -> None:
    brain = BrainHistory.model_validate(_load(BRAIN))
    assert brain.value_stream == "Retirement-Services"
    assert len(brain.snapshots) == 2  # history is needed for scope-creep detection
    latest = brain.snapshots[-1].releases[0]
    assert latest.ir_name == "Launch 36 - Unified Onboarding"
    assert latest.summary.closed == 230
    assert latest.e2e_latest is not None and latest.e2e_latest.passed == 156


def test_environment_and_dependency_parse_real_fixtures() -> None:
    env = EnvironmentInput.model_validate(_load(GOLDEN / "environment.json"))
    dep = DependencyInput.model_validate(_load(GOLDEN / "dependency.json"))
    assert env.components, "environment must carry at least one component"
    assert dep.dependencies, "dependency must carry at least one dependency"


def test_input_contract_ignores_unknown_upstream_fields() -> None:
    env = EnvironmentInput.model_validate(
        {
            "components": [{"name": "API", "provisioning": "validated", "stability": "stable"}],
            "future_field": 123,
        }
    )
    assert not hasattr(env, "future_field")


def test_e2e_absent_is_allowed() -> None:
    brain = BrainHistory.model_validate(_load(BRAIN))
    data = brain.snapshots[-1].releases[0].model_dump()
    data["e2e_latest"] = None
    assert (
        BrainHistory.model_validate(
            {"value_stream": "x", "snapshots": [{"date": "2026-05-28", "releases": [data]}]}
        )
        .snapshots[0]
        .releases[0]
        .e2e_latest
        is None
    )


@pytest.mark.parametrize("bad_score", [-0.1, 1.1])
def test_dimension_result_rejects_out_of_range_score(bad_score: float) -> None:
    with pytest.raises(ValidationError):
        DimensionResult(dimension=DimensionName.SCOPE, score=bad_score, confidence=0.5)


def test_rrr_model_is_frozen_and_strict() -> None:
    res = DimensionResult(dimension=DimensionName.SCOPE, score=0.95, confidence=1.0)
    with pytest.raises(ValidationError):
        res.score = 0.5  # frozen value object
    with pytest.raises(ValidationError):
        DimensionResult(
            dimension=DimensionName.SCOPE, score=0.9, confidence=1.0, typo=1
        )  # extra field forbidden


def test_assessment_output_minimal_construction_and_schema_version() -> None:
    out = AssessmentOutputModel(
        release="Launch 36 - Unified Onboarding",
        verdict=Verdict.GO,
        score=96,
        audit_trail=AuditTrail(provider="RuleBasedProvider"),
    )
    assert out.schema_version == "1.0.0"
    dumped = out.model_dump(mode="json")
    assert dumped["verdict"] == "GO" and dumped["score"] == 96


def test_iso_millis_serialises_with_millisecond_precision() -> None:
    ts = datetime(2026, 6, 14, 10, 0, 0, 123456, tzinfo=UTC)
    assert iso_millis(ts) == "2026-06-14T10:00:00.123Z"
