"""Base collector interface, configuration, and result types (ADR-0023).

Every dimension data collector extends ``BaseCollector``. The ``collect()``
method returns a raw dict that ``CollectorRunner.run()`` validates against the
dimension's ``InputContract`` before writing to ``data/<dimension>.json``.

``CollectorConfig`` carries runtime context (release name, output directory,
skip-optional flag) injected by the CLI or UI surface — collectors themselves
never read config files or environment variables directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CollectorConfig:
    """Runtime context passed to every ``BaseCollector.collect()`` call.

    Keeps collectors free of file-system knowledge and CLI coupling; the
    runner owns the write path.
    """

    release: str
    data_dir: Path
    skip_optional: bool = False


@dataclass
class CollectorResult:
    """Validated output produced by a completed ``CollectorRunner.run()`` call.

    ``data`` holds the validated, JSON-serialisable dict written to disk.
    ``collected_at`` mirrors the ``captured_at`` field stamped into that dict.
    """

    dimension: str
    data: dict[str, Any] = field(default_factory=dict)
    collected_at: str = ""


class BaseCollector(ABC):
    """Abstract base for all dimension data collectors (ADR-0023).

    Subclasses implement ``collect()`` for one dimension. The base imposes no
    I/O constraints on that method — interactive, adapter-backed, and test
    implementations are all valid subclasses.
    """

    @property
    @abstractmethod
    def dimension(self) -> str:
        """``DimensionName.value`` string identifying the dimension this collector targets."""
        ...

    @abstractmethod
    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Gather and return a raw dict for this dimension.

        The returned dict is validated against the dimension's ``InputContract``
        by ``CollectorRunner.run()`` before being written to disk. Implementations
        should not write files directly.

        Args:
            config: Runtime context (release name, output directory, flags).

        Returns:
            Raw key→value dict matching the dimension's ``InputContract`` schema.
        """
        ...
