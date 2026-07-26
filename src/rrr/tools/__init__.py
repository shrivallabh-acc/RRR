"""Tool layer — modular, recorded, timed (FR-10, FR-11, NFR-7).

``BaseTool`` protocol: ``name`` + ``invoke(**params)`` — new tools are addable
without modifying assessors. ``ToolRunner`` enforces a timeout (threading) and
records a ``ToolInvocationModel`` per call, raising ``ToolTimeoutError`` /
``ToolInvocationError`` (each carrying the failed invocation). ``RKTBrainReader``
is the first tool: it reads the brain extract (ADR-0012). Source readers for all
supplementary dimensions live in ``source_reader`` (FR-3, FR-5, ADR-0016).
"""

from __future__ import annotations

from rrr.tools.base import BaseTool, ToolRunResult
from rrr.tools.brain_reader import (
    LATEST,
    TOOL_NAME,
    BrainReadResult,
    PlannedSPPoint,
    RKTBrainReader,
)
from rrr.tools.runner import DEFAULT_TOOL_TIMEOUT, ToolRunner
from rrr.tools.source_reader import (
    DEFAULT_SOURCE_TIMEOUT,
    AccessibilitySourceReader,
    ArchitectureDriftSourceReader,
    ArchitectureFitnessSourceReader,
    AuditabilitySourceReader,
    DataReconciliationSourceReader,
    DependencyRiskSourceReader,
    DependencySourceReader,
    DisasterRecoverySourceReader,
    EnvironmentSourceReader,
    FailureModeSourceReader,
    ObservabilitySourceReader,
    OperabilitySourceReader,
    OperationalSourceReader,
    PerformanceSourceReader,
    ProductionReadinessSourceReader,
    RollbackSourceReader,
    SecuritySourceReader,
)

__all__ = [
    "BaseTool",
    "ToolRunResult",
    "ToolRunner",
    "DEFAULT_TOOL_TIMEOUT",
    "RKTBrainReader",
    "BrainReadResult",
    "PlannedSPPoint",
    "LATEST",
    "TOOL_NAME",
    "EnvironmentSourceReader",
    "DependencySourceReader",
    "OperationalSourceReader",
    "OperabilitySourceReader",
    "ObservabilitySourceReader",
    "RollbackSourceReader",
    "SecuritySourceReader",
    "PerformanceSourceReader",
    "AccessibilitySourceReader",
    "AuditabilitySourceReader",
    "DisasterRecoverySourceReader",
    "DataReconciliationSourceReader",
    "FailureModeSourceReader",
    "DependencyRiskSourceReader",
    "ProductionReadinessSourceReader",
    "ArchitectureFitnessSourceReader",
    "ArchitectureDriftSourceReader",
    "DEFAULT_SOURCE_TIMEOUT",
]
