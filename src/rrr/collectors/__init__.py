"""Collectors package — data collection layer for RRR dimension JSON files (ADR-0023).

The collection system has three layers:

1. ``CollectorRunner`` (runner.py) — framework-agnostic business logic: freshness
   checks (``status()``) and validated write (``run()``). Called identically from
   the CLI and the ``rrr-ui`` Collect screen.

2. ``BaseCollector`` ABC (base.py) + ``InteractiveCollector`` (interactive.py) —
   Phase-1 interactive implementation that generates Click prompts automatically
   from each dimension's ``InputContract`` Pydantic schema.

3. ``rrr-collect`` CLI (_cli.py) — Click command wired in ``pyproject.toml``.

The ``CollectorRegistry`` (registry.py) maps dimension name strings to their
``InputContract`` model classes; both the CLI and runner use it for lookups.
"""

from rrr.collectors.base import BaseCollector, CollectorConfig, CollectorResult
from rrr.collectors.interactive import InteractiveCollector
from rrr.collectors.registry import CollectorRegistry
from rrr.collectors.runner import CollectorRunner, CollectorStatus, DimensionStatusReport

__all__ = [
    "BaseCollector",
    "CollectorConfig",
    "CollectorResult",
    "InteractiveCollector",
    "CollectorRegistry",
    "CollectorRunner",
    "CollectorStatus",
    "DimensionStatusReport",
]
