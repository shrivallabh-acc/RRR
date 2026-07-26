"""Pydantic v2 data models — the typed contracts that cross every boundary.

Three groups (ADR-0004, NFR-5):

* **Input contracts** (``InputContract`` base, tolerant of unknown upstream
  fields): the brain extract (``BrainHistory`` & friends, ADR-0012) and the
  RRR-owned environment/dependency sources.
* **Internal/output value objects** (``RRRModel`` base, frozen + strict):
  ``DimensionResult``, the audit-trail records, and the versioned
  ``AssessmentOutputModel`` ("1.0.0").
* **LLM I/O** (``DimensionReasoning``, ``VerdictSynthesis``): the
  schema-validated structured outputs ``LLMProvider.reason()`` returns.

Models carry shape only; deterministic scoring lives in the assessors (M3).
"""

from __future__ import annotations

from rrr.models.assessment import (
    SCHEMA_VERSION,
    AssessmentOutputModel,
    AuditTrail,
    Benchmark,
    TrendData,
)
from rrr.models.base import InputContract, RRRModel, iso_millis, utc_now
from rrr.models.brain import (
    BrainHistory,
    BrainSnapshot,
    DefectSeverity,
    DefectsOpen,
    E2EPoint,
    PVPoint,
    ReleaseRecord,
    Summary,
    WeeklyPoint,
)
from rrr.models.dependency import DependencyInput, DependencyItem
from rrr.models.dimension import DimensionResult
from rrr.models.enums import (
    DependencyClass,
    DependencyCompletion,
    DimensionName,
    EstimationClass,
    IntegrationStatus,
    ProvisioningStatus,
    ReleaseRiskTier,
    RiskSeverity,
    ScopeClass,
    StabilityStatus,
    TrendDirection,
    Verdict,
)
from rrr.models.environment import ComponentStatus, EnvironmentInput
from rrr.models.evidence import EvidenceRecord, RiskFactor, ToolInvocationModel
from rrr.models.llm import DimensionReasoning, VerdictSynthesis

__all__ = [
    # base
    "RRRModel",
    "InputContract",
    "utc_now",
    "iso_millis",
    # enums
    "Verdict",
    "DimensionName",
    "ReleaseRiskTier",
    "ScopeClass",
    "EstimationClass",
    "ProvisioningStatus",
    "StabilityStatus",
    "DependencyCompletion",
    "IntegrationStatus",
    "DependencyClass",
    "RiskSeverity",
    "TrendDirection",
    # brain input contract
    "BrainHistory",
    "BrainSnapshot",
    "ReleaseRecord",
    "Summary",
    "WeeklyPoint",
    "DefectsOpen",
    "DefectSeverity",
    "PVPoint",
    "E2EPoint",
    # environment / dependency input contracts
    "EnvironmentInput",
    "ComponentStatus",
    "DependencyInput",
    "DependencyItem",
    # evidence / audit value objects
    "ToolInvocationModel",
    "EvidenceRecord",
    "RiskFactor",
    # dimension result
    "DimensionResult",
    # llm structured output
    "DimensionReasoning",
    "VerdictSynthesis",
    # assessment output
    "AssessmentOutputModel",
    "TrendData",
    "Benchmark",
    "AuditTrail",
    "SCHEMA_VERSION",
]
