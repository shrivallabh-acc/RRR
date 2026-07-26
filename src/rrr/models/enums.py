"""Controlled vocabularies shared across the model layer (the ubiquitous language).

Every classification in RRR is a closed enum rather than a free string, so
assessors can match exhaustively and validation is free. Enum *values* match the
wire format of the input contracts (brain-schema.md, env-dep-schema.md,
operational-schema.md) and the output model (requirements FR-8/FR-18) verbatim,
so JSON round-trips cleanly.
"""

from __future__ import annotations

from enum import StrEnum


class ReleaseRiskTier(StrEnum):
    """Release risk tier — selects threshold set and gate-dim exclusions (ADR-0016 items 4-5).

    HOTFIX: small targeted fix; relaxed score thresholds, minimal required dims.
    STANDARD: regular feature release; default thresholds.
    MAJOR: large/high-risk release; stricter thresholds, more required dims.
    """

    HOTFIX = "hotfix"
    STANDARD = "standard"
    MAJOR = "major"


class Verdict(StrEnum):
    """Final release verdict (FR-8). Ordering for cap-gate comparison lives with
    the orchestrator (ADR-0013), not here."""

    GO = "GO"
    NO_GO = "NO_GO"
    CONDITIONAL = "CONDITIONAL"
    INCOMPLETE = "INCOMPLETE"


class DimensionName(StrEnum):
    """Assessment dimension names (FR-1..FR-5, ADR-0016).

    FR-1..FR-5: Scope, Estimation, Environment, Test Readiness, Dependency.
    ADR-0016 item 1: OPERATIONAL (superseded by item-7 split; kept for SQLite
    backward compatibility with historical assessment records).
    ADR-0016 item 7: OPERATIONAL split into OPERABILITY (weighted 0.07),
    OBSERVABILITY (weighted 0.03), and ROLLBACK (gate-only).
    ADR-0016 items 2-3: SECURITY and PERFORMANCE (gate-only, opt-in).
    """

    SCOPE = "scope"
    ESTIMATION = "estimation"
    ENVIRONMENT = "environment"
    TEST_READINESS = "test_readiness"
    DEPENDENCY = "dependency"
    # Superseded by the item-7 split — retained for backward compat with SQLite records.
    OPERATIONAL = "operational"
    # ADR-0016 item 7 split assessors (replace OPERATIONAL in the live pipeline).
    OPERABILITY = "operability"
    OBSERVABILITY = "observability"
    ROLLBACK = "rollback"
    # ADR-0016 items 2-3 — gate-only, opt-in via sources config.
    SECURITY = "security"
    PERFORMANCE = "performance"
    # ADR-0016 items 8-16 — gate-only assessors, all opt-in via sources config.
    ACCESSIBILITY = "accessibility"
    AUDITABILITY = "auditability"
    DISASTER_RECOVERY = "disaster_recovery"
    DATA_RECONCILIATION = "data_reconciliation"
    FAILURE_MODE = "failure_mode"
    DEPENDENCY_RISK = "dependency_risk"
    PRODUCTION_READINESS = "production_readiness"
    ARCHITECTURE_FITNESS = "architecture_fitness"
    ARCHITECTURE_DRIFT = "architecture_drift"


class ScopeClass(StrEnum):
    """Scope delivery classification (FR-1): completion >=0.90 / >=0.50 / <0.50."""

    DELIVERED = "delivered"
    PARTIALLY_DELIVERED = "partially_delivered"
    NOT_DELIVERED = "not_delivered"


class EstimationClass(StrEnum):
    """Earned-value variance classification (FR-2), tolerance +/-10%."""

    OVER = "over"
    UNDER = "under"
    WITHIN_TOLERANCE = "within_tolerance"


class ProvisioningStatus(StrEnum):
    """Environment component provisioning state (FR-3). Drives the numeric score."""

    VALIDATED = "validated"
    CONFIGURED = "configured"
    PROVISIONED = "provisioned"
    MISSING = "missing"


class StabilityStatus(StrEnum):
    """Environment component operational state (FR-3). Drives risk severity, not score."""

    STABLE = "stable"
    DEGRADED = "degraded"
    DOWN = "down"


class DependencyCompletion(StrEnum):
    """Dependency completion state (FR-5)."""

    COMPLETE = "complete"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"


class IntegrationStatus(StrEnum):
    """Dependency integration-validation state (FR-5)."""

    PASSED = "passed"
    NOT_VALIDATED = "not_validated"
    FAILED = "failed"


class DependencyClass(StrEnum):
    """Per-dependency risk classification (FR-5)."""

    BLOCKING = "blocking"
    AT_RISK = "at_risk"
    ON_TRACK = "on_track"


class RiskSeverity(StrEnum):
    """Severity label attached to a risk factor (env gap severity reuses this:
    down=critical, degraded=major, stable=minor — FR-3)."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class TrendDirection(StrEnum):
    """Per-dimension trend vs the previous assessment (FR-9): delta>0.05 / <-0.05 / else.

    Also reused for the test defect-trend direction (FR-4)."""

    IMPROVING = "improving"
    DEGRADING = "degrading"
    STABLE = "stable"


class PipelineStatus(StrEnum):
    """Deployment pipeline health for the Operational dimension (ADR-0016)."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"


class RollbackStatus(StrEnum):
    """Rollback plan completeness for the Operational dimension (ADR-0016)."""

    DOCUMENTED = "documented"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class SastStatus(StrEnum):
    """Static Application Security Testing scan outcome (ADR-0016, Security dimension)."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class DastStatus(StrEnum):
    """Dynamic Application Security Testing scan outcome (ADR-0016, Security dimension)."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class PerformanceTestStatus(StrEnum):
    """Load / performance test execution outcome (ADR-0016, Performance dimension)."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
