"""CollectorRegistry — mapping from dimension name to InputContract model class (ADR-0023).

The registry is the single source of truth for which dimensions support interactive
collection and which ``InputContract`` model validates each dimension's data file.

``DIMENSION_MODELS`` covers all supplementary dimensions whose data lives in
``data/<dimension>.json`` and is authored (or collected) outside the brain pipeline.
Brain-backed dimensions (scope, estimation, test_readiness, dependency) are populated
from ``brain/*.json`` via ``rrr-ingest`` and are therefore excluded.

``CollectorRegistry`` wraps the dict with a typed, testable interface that the CLI
and UI surfaces use — they never reference ``DIMENSION_MODELS`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rrr.models.accessibility import AccessibilityInput
from rrr.models.architecture_drift import ArchitectureDriftInput
from rrr.models.architecture_fitness import ArchitectureFitnessInput
from rrr.models.auditability import AuditabilityInput
from rrr.models.base import InputContract
from rrr.models.data_reconciliation import DataReconciliationInput
from rrr.models.dependency_risk import DependencyRiskInput
from rrr.models.disaster_recovery import DisasterRecoveryInput
from rrr.models.failure_mode import FailureModeInput
from rrr.models.observability import ObservabilityInput
from rrr.models.operability import OperabilityInput
from rrr.models.performance import PerformanceInput
from rrr.models.production_readiness import ProductionReadinessInput
from rrr.models.rollback import RollbackInput
from rrr.models.security import SecurityInput

if TYPE_CHECKING:
    pass

# Ordered list of supplementary dimensions (display order for --status output).
DIMENSION_MODELS: dict[str, type[InputContract]] = {
    "operability": OperabilityInput,
    "observability": ObservabilityInput,
    "rollback": RollbackInput,
    "security": SecurityInput,
    "performance": PerformanceInput,
    "accessibility": AccessibilityInput,
    "auditability": AuditabilityInput,
    "disaster_recovery": DisasterRecoveryInput,
    "data_reconciliation": DataReconciliationInput,
    "failure_mode": FailureModeInput,
    "dependency_risk": DependencyRiskInput,
    "production_readiness": ProductionReadinessInput,
    "architecture_fitness": ArchitectureFitnessInput,
    "architecture_drift": ArchitectureDriftInput,
}


class CollectorRegistry:
    """Typed interface over ``DIMENSION_MODELS`` (ADR-0023).

    Surfaces use this class rather than the raw dict so the lookup API is
    stable even if the underlying storage changes.
    """

    def __init__(self, models: dict[str, type[InputContract]] | None = None) -> None:
        """Initialise with the default dimension→model mapping or a custom override.

        Args:
            models: Custom mapping (used in tests). Defaults to ``DIMENSION_MODELS``.
        """
        self._models: dict[str, type[InputContract]] = (
            models if models is not None else dict(DIMENSION_MODELS)
        )

    def dimensions(self) -> list[str]:
        """Return the ordered list of dimension names this registry covers."""
        return list(self._models.keys())

    def model_for(self, dimension: str) -> type[InputContract]:
        """Return the ``InputContract`` class for ``dimension``.

        Args:
            dimension: A ``DimensionName.value`` string.

        Returns:
            The ``InputContract`` subclass registered for that dimension.

        Raises:
            KeyError: If ``dimension`` is not registered.
        """
        if dimension not in self._models:
            raise KeyError(
                f"Dimension {dimension!r} is not in the collector registry. "
                f"Known dimensions: {', '.join(self._models)}"
            )
        return self._models[dimension]

    def is_registered(self, dimension: str) -> bool:
        """Return True if ``dimension`` has a registered model."""
        return dimension in self._models
