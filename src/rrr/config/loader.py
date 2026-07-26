"""``ConfigLoader`` — load, merge, and validate RRR configuration (FR-15).

Precedence (lowest to highest): bundled ``default_config.yaml`` → optional user
config file → in-process overrides. Dicts deep-merge; scalars and lists replace.
The merged mapping is validated by :class:`RRRConfig`; any failure is re-raised
as :class:`ConfigurationError` with a readable, field-pathed error list.

Environment-variable interpolation (T-04): any string value of the form
``${VAR_NAME}`` is replaced with the value of ``os.environ["VAR_NAME"]``
before Pydantic validation.  Missing variables raise :class:`ConfigurationError`
immediately so the operator knows exactly which variable to set.  This allows
API keys and passwords to live in environment variables (e.g. Kubernetes Secrets,
AWS Secrets Manager) rather than in YAML files that may be committed to version
control.
"""

from __future__ import annotations

import copy
import os
import re
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rrr.config.schema import RRRConfig
from rrr.errors import ConfigurationError

# Matches ${VAR_NAME} — uppercase letters, digits, and underscores only.
# Deliberately restrictive: lowercase or special chars are not env-var names.
_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")

DEFAULT_CONFIG_FILENAME = "default_config.yaml"


def _interpolate_env(obj: Any) -> Any:
    """Recursively replace ``${VAR_NAME}`` placeholders with environment-variable values.

    Walks the merged YAML structure (dicts, lists, scalars) before Pydantic
    validation so secrets never need to appear in YAML files.  Raises
    :class:`ConfigurationError` immediately if a referenced variable is unset —
    a clear error is better than a cryptic Pydantic type mismatch downstream.
    """
    if isinstance(obj, str):
        def _replace(match: re.Match[str]) -> str:
            """Return the env-var value or raise ConfigurationError if unset."""
            name = match.group(1)
            value = os.environ.get(name)
            if value is None:
                raise ConfigurationError(
                    f"${{{name}}} is referenced in the config but is not set in the environment"
                )
            return value

        return _ENV_VAR_RE.sub(_replace, obj)
    if isinstance(obj, dict):
        return {k: _interpolate_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_env(item) for item in obj]
    return obj


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (returns a new dict).

    Nested dicts merge key-by-key; any non-dict value (scalar or list) replaces.

    Tagged-union exception: if both sides are dicts carrying a ``type`` key and the
    values differ, the override *replaces* the sub-tree wholesale rather than
    merging. This prevents stale sibling keys from one variant (e.g. a file
    source's ``path``) leaking into another (an ``api`` source's ``url``).
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        existing = merged.get(key)
        if (
            isinstance(existing, dict)
            and isinstance(value, dict)
            and not _switches_type(existing, value)
        ):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _switches_type(base: dict[str, Any], override: dict[str, Any]) -> bool:
    """True if both dicts tag a ``type`` and the override changes it (variant switch)."""
    return "type" in base and "type" in override and base["type"] != override["type"]


def _load_yaml(text: str, source: str) -> dict[str, Any]:
    """Parse a YAML string and return it as a plain dict.

    ``yaml.safe_load`` is used (not full_load) so only basic Python types are
    constructed — no arbitrary Python object instantiation from YAML tags.
    An empty file is treated as an empty config (not an error), because a user
    might legitimately override only a small subset of settings.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"failed to parse YAML from {source}", [str(exc)]) from exc
    if data is None:
        # Empty YAML file — treat as no overrides.
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"config root must be a mapping, got {type(data).__name__} from {source}"
        )
    return data


class ConfigLoader:
    """Loads the bundled defaults, layers overrides, and validates."""

    @staticmethod
    def default_mapping() -> dict[str, Any]:
        """The bundled ``default_config.yaml`` as a raw mapping (pre-validation)."""
        resource = resources.files("rrr.config").joinpath(DEFAULT_CONFIG_FILENAME)
        return _load_yaml(resource.read_text(encoding="utf-8"), source=DEFAULT_CONFIG_FILENAME)

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> RRRConfig:
        """Return a validated :class:`RRRConfig`.

        :param config_path: optional user YAML file merged over the defaults.
        :param overrides: optional in-process mapping merged last (highest precedence).
        :raises ConfigurationError: on parse, merge, or validation failure.
        """
        merged = cls.default_mapping()

        if config_path is not None:
            path = Path(config_path)
            if not path.is_file():
                raise ConfigurationError(f"config file not found: {path}")
            user = _load_yaml(path.read_text(encoding="utf-8"), source=str(path))
            merged = _deep_merge(merged, user)

        if overrides:
            merged = _deep_merge(merged, overrides)

        # Substitute ${VAR} placeholders before Pydantic sees the values.
        merged = _interpolate_env(merged)

        try:
            return RRRConfig.model_validate(merged)
        except ValidationError as exc:
            raise ConfigurationError("invalid configuration", cls._format_errors(exc)) from exc

    @staticmethod
    def _format_errors(exc: ValidationError) -> list[str]:
        """Convert Pydantic validation errors into readable field-pathed strings.

        Each error gets a dotted location path (e.g. ``thresholds.go``) so the
        person reading the ConfigurationError knows exactly which YAML key to fix,
        without having to decode Pydantic's internal error format themselves.
        """
        problems: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            problems.append(f"{loc}: {err['msg']}")
        return problems
