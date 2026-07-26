"""Configuration loading and validation (FR-15, ADR-0010).

``ConfigLoader`` reads the bundled ``default_config.yaml``, deep-merges an optional
user file and in-process overrides, and validates the result into a frozen
:class:`RRRConfig` — raising :class:`~rrr.errors.ConfigurationError` with a
detailed, field-pathed error list. Weights must sum to 1.0; ``api`` data sources
must resolve to an allow-listed (local) host.
"""

from __future__ import annotations

from rrr.config.loader import ConfigLoader
from rrr.config.schema import (
    ApiSource,
    AssessorsConfig,
    BrainSourceConfig,
    ClaudeConfig,
    DataSource,
    FileSource,
    GatesConfig,
    LocalLLMConfig,
    MemoryConfig,
    PersistenceConfig,
    ProviderConfig,
    ProviderType,
    RRRConfig,
    SourcesConfig,
    TestReadinessAssessorConfig,
    ThresholdsConfig,
    TimeoutsConfig,
    TrendConfig,
    WeightsConfig,
)

__all__ = [
    "ConfigLoader",
    "RRRConfig",
    "WeightsConfig",
    "ThresholdsConfig",
    "TrendConfig",
    "GatesConfig",
    "TimeoutsConfig",
    "PersistenceConfig",
    "ProviderConfig",
    "ProviderType",
    "LocalLLMConfig",
    "ClaudeConfig",
    "SourcesConfig",
    "BrainSourceConfig",
    "FileSource",
    "ApiSource",
    "DataSource",
    "AssessorsConfig",
    "TestReadinessAssessorConfig",
    "MemoryConfig",
]
