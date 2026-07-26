"""InteractiveCollector — Pydantic-schema-driven Click prompt generator (ADR-0023).

Introspects a dimension's ``InputContract`` Pydantic model to generate type-appropriate
Click prompts automatically — no per-dimension hardcoding required.

Field-type dispatch rules:
  Enum subclass  → click.Choice of enum values
  bool           → click.confirm
  int / float    → typed click.prompt
  str            → text click.prompt (empty string collapses to None for Optional[str])
  dict / list    → skipped with a visible advisory message (edit JSON directly)
  Other complex  → skipped with a visible advisory message

Auto-filled fields (never prompted):
  schema_version, release, captured_at

Update mode: loads any existing ``data/<dimension>.json`` as defaults before prompting,
so re-running the collector shows the previous values and allows selective edits.
"""

from __future__ import annotations

import enum as enum_module
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import click
from pydantic.fields import FieldInfo

from rrr.collectors.base import BaseCollector, CollectorConfig
from rrr.models.base import InputContract, iso_millis

# Fields that are filled from context — never presented to the user.
_AUTO_FIELDS = frozenset({"schema_version", "release", "captured_at"})


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Extract the inner type from Optional[T] (i.e. Union[T, None]).

    Returns (inner_type, True) when annotation is Optional[T], and
    (annotation, False) for all other annotations including plain unions.
    """
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0], True
    return annotation, False


def _is_enum_class(t: Any) -> bool:
    """Return True if t is a concrete Enum subclass (not the Enum base itself)."""
    return inspect.isclass(t) and issubclass(t, enum_module.Enum)


def _is_complex_origin(inner: Any) -> bool:
    """Return True if the type origin is dict or list — cannot be prompted interactively."""
    return inner in (dict, list) or get_origin(inner) in (dict, list)


class InteractiveCollector(BaseCollector):
    """Generates Click prompts from a dimension's ``InputContract`` schema (ADR-0023).

    Bind to one dimension at construction time. Each ``collect()`` call introspects
    ``model_class.model_fields`` and prompts the user for each field. Existing
    file values become the prompt defaults (update mode).
    """

    def __init__(self, dimension_name: str, model_class: type[InputContract]) -> None:
        """Bind this collector to one dimension and its ``InputContract`` class.

        Args:
            dimension_name: ``DimensionName.value`` string — also the JSON file stem.
            model_class: The ``InputContract`` subclass whose fields drive the prompts.
        """
        self._dimension_name = dimension_name
        self._model_class = model_class

    @property
    def dimension(self) -> str:
        """Return the dimension name (``DimensionName.value``) this collector targets."""
        return self._dimension_name

    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Prompt for each field and return the completed dict.

        Loads any existing ``data/<dimension>.json`` as defaults (update mode),
        then presents one prompt per non-auto field. The caller (``CollectorRunner``)
        validates the returned dict against the model and writes the file.

        Args:
            config: Runtime context — release name, output directory, skip_optional flag.

        Returns:
            Raw key→value dict ready for ``model_class.model_validate()``.
        """
        existing = _load_existing(config.data_dir / f"{self._dimension_name}.json")

        result: dict[str, Any] = {
            "schema_version": "1.0.0",
            "release": config.release,
            "captured_at": iso_millis(datetime.now(UTC)),
        }

        click.echo(f"\nCollecting data for dimension: {self._dimension_name}")
        click.echo("─" * 60)

        for name, field_info in self._model_class.model_fields.items():
            if name in _AUTO_FIELDS:
                continue

            # Use None as the default when the field has no model-level default.
            raw_default = None if field_info.is_required() else field_info.default

            # Prefer value from existing file over model default (update mode).
            effective_default = existing.get(name, raw_default)

            result[name] = _prompt_field(name, field_info, effective_default, config.skip_optional)

        return result


def _load_existing(path: Path) -> dict[str, Any]:
    """Load a JSON data file as a defaults dict; return {} when the file is absent or invalid.

    Silent failure is intentional — a missing or malformed file is treated as
    "no prior data" and the collector falls back to model defaults.
    """
    try:
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return result
    except (OSError, ValueError):
        return {}


def _prompt_field(
    name: str,
    field_info: FieldInfo,
    default: Any,
    skip_optional: bool,
) -> Any:
    """Dispatch to the appropriate Click prompt based on the field's resolved type.

    Handles: Enum → Choice; bool → confirm; int/float/str → typed prompt.
    Complex types (dict, list) are skipped with an advisory message.
    When ``skip_optional`` is True, Optional fields with a non-None default are
    kept silently rather than prompted.
    """
    annotation = field_info.annotation
    inner_type, is_optional = _unwrap_optional(annotation)

    # Optional field with a usable default — skip the prompt when skip_optional is set.
    if is_optional and skip_optional and default is not None:
        click.echo(f"  [skip]  {name}: keeping existing value ({default!r})")
        return default

    # Complex types (dict, list) cannot be collected interactively.
    if _is_complex_origin(inner_type):
        if default not in (None, {}, []):
            click.echo(f"  [keep]  {name}: complex value retained from existing file")
        else:
            click.echo(f"  [skip]  {name}: complex type — edit this field in the JSON file")
        return default

    label = f"  {name}"

    # Enum → click.Choice from enum member values.
    if _is_enum_class(inner_type):
        choices = [e.value for e in inner_type]
        str_default = default.value if isinstance(default, enum_module.Enum) else (
            default if isinstance(default, str) and default in choices else choices[0]
        )
        return click.prompt(
            label, type=click.Choice(choices, case_sensitive=False), default=str_default
        )

    # bool → confirm.
    if inner_type is bool:
        return click.confirm(label, default=bool(default) if default is not None else False)

    # int → integer prompt.
    if inner_type is int:
        return click.prompt(label, type=int, default=int(default) if default is not None else 0)

    # float → float prompt.
    if inner_type is float:
        return click.prompt(
            label, type=float, default=float(default) if default is not None else 0.0
        )

    # str → text prompt (empty string collapses to None for Optional[str] fields).
    if inner_type is str:
        str_default = str(default) if default is not None else ""
        entered = click.prompt(label, default=str_default, show_default=(str_default != ""))
        if is_optional and entered == "":
            return None
        return entered

    # Unsupported type — keep the default silently.
    click.echo(f"  [skip]  {name}: unsupported type ({inner_type!r}) — edit JSON directly")
    return default
