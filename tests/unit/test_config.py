"""Tests for ConfigLoader + the config schema (FR-15, NFR-8, T-02, T-04)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rrr.config import ConfigLoader, ProviderType, RRRConfig
from rrr.errors import ConfigurationError


def test_bundled_defaults_load_and_validate() -> None:
    cfg = ConfigLoader.load()
    assert isinstance(cfg, RRRConfig)
    assert cfg.schema_version == "1.0.0"
    assert cfg.provider.type is ProviderType.RULE_BASED
    assert cfg.thresholds.minimum_assessors == 4
    # ADR-0011 weights present and summing to 1.0
    assert cfg.weights.test_readiness == 0.27


def test_defaults_are_frozen() -> None:
    cfg = ConfigLoader.load()
    with pytest.raises(ValidationError):
        cfg.thresholds.go = 0.5  # type: ignore[misc]


def test_overrides_deep_merge_without_clobbering_siblings() -> None:
    cfg = ConfigLoader.load(overrides={"thresholds": {"go": 0.9}})
    assert cfg.thresholds.go == 0.9
    assert cfg.thresholds.no_go == 0.40  # sibling preserved by deep merge
    assert cfg.thresholds.minimum_assessors == 4


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"weights": {"estimation": 0.50}})
    assert any("sum to 1.0" in e for e in exc.value.errors)


def test_go_must_exceed_no_go() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"thresholds": {"go": 0.30, "no_go": 0.40}})
    assert any("greater than" in e for e in exc.value.errors)


def test_gate_cap_cannot_be_go() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"gates": {"blocker_defects": "GO"}})
    assert any("NO_GO, CONDITIONAL" in e for e in exc.value.errors)


def test_api_source_host_must_be_allow_listed() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(
            overrides={
                "sources": {"environment": {"type": "api", "url": "http://evil.example.com/env"}}
            }
        )
    assert any("not allow-listed" in e for e in exc.value.errors)


def test_localhost_api_source_is_accepted() -> None:
    cfg = ConfigLoader.load(
        overrides={"sources": {"dependency": {"type": "api", "url": "http://127.0.0.1:8002/dep"}}}
    )
    assert cfg.sources.dependency.type == "api"


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"weights": {"made_up_dimension": 0.0}})
    assert any("made_up_dimension" in e or "Extra inputs" in e for e in exc.value.errors)


def test_missing_config_file_raises() -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        ConfigLoader.load(config_path="does/not/exist.yaml")


def test_invalid_snapshot_form_rejected() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"sources": {"brain": {"snapshot": "last-week"}}})
    assert any("snapshot" in e for e in exc.value.errors)


# --- T-04: env-var ${VAR} interpolation -------------------------------------------------------


def test_env_var_interpolation_substitutes_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RRR_TEST_VAR", "test-value")
    cfg = ConfigLoader.load(overrides={"sources": {"brain": {"value_stream": "${RRR_TEST_VAR}"}}})
    assert cfg.sources.brain.value_stream == "test-value"


def test_env_var_interpolation_raises_on_unset_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RRR_MISSING_VAR", raising=False)
    with pytest.raises(ConfigurationError, match="RRR_MISSING_VAR"):
        ConfigLoader.load(
            overrides={"sources": {"brain": {"value_stream": "${RRR_MISSING_VAR}"}}}
        )


def test_env_var_interpolation_works_in_nested_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RRR_BRAIN_DIR", "./my-brain")
    cfg = ConfigLoader.load(overrides={"sources": {"brain": {"dir": "${RRR_BRAIN_DIR}"}}})
    assert cfg.sources.brain.dir == "./my-brain"


def test_env_var_no_op_on_plain_string() -> None:
    cfg = ConfigLoader.load(overrides={"sources": {"brain": {"value_stream": "plain-value"}}})
    assert cfg.sources.brain.value_stream == "plain-value"


# --- T-02: UiConfig model + HTTP Basic Auth ---------------------------------------------------


def test_ui_config_defaults_to_no_auth() -> None:
    cfg = ConfigLoader.load()
    assert cfg.ui.auth_user is None
    assert cfg.ui.auth_password is None


def test_ui_config_accepts_paired_credentials() -> None:
    cfg = ConfigLoader.load(overrides={"ui": {"auth_user": "admin", "auth_password": "s3cr3t"}})
    assert cfg.ui.auth_user == "admin"
    assert cfg.ui.auth_password == "s3cr3t"


def test_ui_config_rejects_user_without_password() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"ui": {"auth_user": "admin"}})
    assert any("both be set or both be null" in e for e in exc.value.errors)


def test_ui_config_rejects_password_without_user() -> None:
    with pytest.raises(ConfigurationError) as exc:
        ConfigLoader.load(overrides={"ui": {"auth_password": "s3cr3t"}})
    assert any("both be set or both be null" in e for e in exc.value.errors)


def test_ui_config_with_env_var_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RRR_UI_PASSWORD", "my-pass")
    cfg = ConfigLoader.load(
        overrides={"ui": {"auth_user": "admin", "auth_password": "${RRR_UI_PASSWORD}"}}
    )
    assert cfg.ui.auth_password == "my-pass"
