"""Assessment dimensions — deterministic score + LLM reasoning, one ``DimensionResult`` each.

``BaseAssessor`` (ABC) is a template method: subclasses implement ``_assess`` (the
deterministic core) and the base orchestrates reasoning, confidence (FR-12), and
``DimensionResult`` assembly. Helpers: ``invoke_tool``, ``calculate_confidence``,
``build_evidence``, ``reason`` (guardrail fallback), ``reset``.

Concrete assessors (FR-1..FR-5, ADR-0016):
  Core weighted: ScopeAssessor, EstimationAssessor, EnvironmentAssessor,
    TestReadinessAssessor, DependencyAssessor, OperabilityAssessor,
    ObservabilityAssessor (opt-in when observability source configured).
  Gate-only opt-in (items 2-3): RollbackAssessor, SecurityComplianceAssessor,
    PerformanceAssessor.
  Gate-only opt-in (items 8-16): AccessibilityAssessor, AuditabilityAssessor,
    DisasterRecoveryAssessor, DataReconciliationAssessor, FailureModeAssessor,
    DependencyRiskAssessor, ProductionReadinessAssessor, ArchitectureFitnessAssessor,
    ArchitectureDriftAssessor.
  Superseded (kept for backward compat): OperationalAssessor.
(FR-12, FR-13, NFR-7)
"""

from __future__ import annotations

from rrr.assessors.accessibility import AccessibilityAssessor
from rrr.assessors.architecture_drift import ArchitectureDriftAssessor
from rrr.assessors.architecture_fitness import ArchitectureFitnessAssessor
from rrr.assessors.auditability import AuditabilityAssessor
from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.assessors.data_reconciliation import DataReconciliationAssessor
from rrr.assessors.dependency import DependencyAssessor
from rrr.assessors.dependency_risk import DependencyRiskAssessor
from rrr.assessors.disaster_recovery import DisasterRecoveryAssessor
from rrr.assessors.environment import EnvironmentAssessor
from rrr.assessors.estimation import EstimationAssessor
from rrr.assessors.failure_mode import FailureModeAssessor
from rrr.assessors.observability import ObservabilityAssessor
from rrr.assessors.operability import OperabilityAssessor
from rrr.assessors.operational import OperationalAssessor
from rrr.assessors.performance import PerformanceAssessor
from rrr.assessors.production_readiness import ProductionReadinessAssessor
from rrr.assessors.rollback import RollbackAssessor
from rrr.assessors.scope import ScopeAssessor
from rrr.assessors.security import SecurityComplianceAssessor
from rrr.assessors.test_readiness import TestReadinessAssessor

__all__ = [
    "BaseAssessor",
    "DeterministicAssessment",
    "ScopeAssessor",
    "EstimationAssessor",
    "TestReadinessAssessor",
    "EnvironmentAssessor",
    "DependencyAssessor",
    "OperabilityAssessor",
    "ObservabilityAssessor",
    "RollbackAssessor",
    "OperationalAssessor",
    "SecurityComplianceAssessor",
    "PerformanceAssessor",
    "AccessibilityAssessor",
    "AuditabilityAssessor",
    "DisasterRecoveryAssessor",
    "DataReconciliationAssessor",
    "FailureModeAssessor",
    "DependencyRiskAssessor",
    "ProductionReadinessAssessor",
    "ArchitectureFitnessAssessor",
    "ArchitectureDriftAssessor",
]
