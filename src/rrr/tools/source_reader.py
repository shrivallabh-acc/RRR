"""Source readers for dimension input data — file or localhost API transport.

One base class, seventeen concrete readers (env-dep-schema.md, ADR-0016): JSON is
canonical; a CSV form carries the same rows; an optional ``api`` form fetches
the JSON body from an allow-listed local host. Local-first is enforced here
too (NFR-8/ADR-0010): an API host outside ``allowed_hosts`` is rejected before
any network call.

Concrete readers: ``EnvironmentSourceReader``, ``DependencySourceReader``,
``OperationalSourceReader`` (superseded by item-7 split, kept for backward compat),
``OperabilitySourceReader``, ``ObservabilitySourceReader``, ``RollbackSourceReader``,
``SecuritySourceReader``, ``PerformanceSourceReader`` (items 1-7); and the nine new
gate-only readers for ADR-0016 items 8-16: ``AccessibilitySourceReader``,
``AuditabilitySourceReader``, ``DisasterRecoverySourceReader``,
``DataReconciliationSourceReader``, ``FailureModeSourceReader``,
``DependencyRiskSourceReader``, ``ProductionReadinessSourceReader``,
``ArchitectureFitnessSourceReader``, ``ArchitectureDriftSourceReader``.
Each validates into its Pydantic input model (FR-3, FR-5, ADR-0016).
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse
from urllib.request import urlopen

from pydantic import BaseModel

from rrr.errors import SourceReadError
from rrr.models.accessibility import AccessibilityInput
from rrr.models.architecture_drift import ArchitectureDriftInput
from rrr.models.architecture_fitness import ArchitectureFitnessInput
from rrr.models.auditability import AuditabilityInput
from rrr.models.data_reconciliation import DataReconciliationInput
from rrr.models.dependency import DependencyInput
from rrr.models.dependency_risk import DependencyRiskInput
from rrr.models.disaster_recovery import DisasterRecoveryInput
from rrr.models.environment import EnvironmentInput
from rrr.models.failure_mode import FailureModeInput
from rrr.models.observability import ObservabilityInput
from rrr.models.operability import OperabilityInput
from rrr.models.operational import OperationalInput
from rrr.models.performance import PerformanceInput
from rrr.models.production_readiness import ProductionReadinessInput
from rrr.models.rollback import RollbackInput
from rrr.models.security import SecurityInput

DEFAULT_SOURCE_TIMEOUT = 10.0
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")


def _http_get(url: str, timeout: float) -> str:
    """Fetch the URL and return the response body as a UTF-8 string.

    The S310 noqa suppresses the Bandit warning about urlopen — the host has
    already been checked against the allow-list before this function is called,
    so the call is safe (NFR-8, ADR-0010).
    """
    with urlopen(url, timeout=timeout) as resp:  # noqa: S310 (host allow-listed by caller)
        data: bytes = resp.read()
    return data.decode("utf-8")


def _as_dict(data: Any, source: str) -> dict[str, Any]:
    """Assert that the parsed data is a JSON object (dict), not a list or scalar.

    Both the environment and dependency schemas are top-level JSON objects, so
    receiving a list or primitive is always a schema mismatch worth reporting
    clearly rather than letting it surface as a confusing KeyError later.
    """
    if not isinstance(data, dict):
        raise SourceReadError(f"source {source} must be a JSON object, got {type(data).__name__}")
    return data


def _parse_csv(text: str, list_key: str) -> dict[str, Any]:
    """Convert a CSV text into the same dict shape that the JSON schema expects.

    csv.DictReader treats the first row as headers. The resulting list of row
    dicts is wrapped in a top-level key (e.g. ``{"components": [...]}`` or
    ``{"dependencies": [...]}``) to match the JSON format so both formats can
    share the same Pydantic validation path.
    """
    rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
    return {list_key: rows}


class _FileApiSourceReader:
    """Shared file/CSV/API transport; subclasses bind a model and CSV list key."""

    tool_name: ClassVar[str]
    model: ClassVar[type[BaseModel]]
    list_key: ClassVar[str]

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        url: str | None = None,
        allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS,
        timeout: float = DEFAULT_SOURCE_TIMEOUT,
    ) -> None:
        if (path is None) == (url is None):
            raise SourceReadError(f"{self.tool_name} requires exactly one of 'path' or 'url'")
        self._path = path
        self._url = url
        self._allowed_hosts = allowed_hosts
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self.tool_name

    def invoke(self, **params: Any) -> BaseModel:
        """BaseTool entry point: load raw data and validate it into the Pydantic model."""
        return self.model.model_validate(self._load())

    def _load(self) -> dict[str, Any]:
        """Route to the correct transport (API or file) based on how the reader was constructed."""
        if self._url is not None:
            return self._load_api(self._url)
        assert self._path is not None  # guaranteed by __init__
        return self._load_file(Path(self._path))

    def _load_api(self, url: str) -> dict[str, Any]:
        """Fetch JSON from a localhost API, enforcing the allow-list before connecting.

        The allow-list check happens here (not in __init__) so it runs on every
        invocation, guarding against any future runtime config mutation.
        """
        host = urlparse(url).hostname
        if host not in self._allowed_hosts:
            raise SourceReadError(
                f"source host {host!r} is not allow-listed {self._allowed_hosts} "
                f"— local-first, NFR-8/ADR-0010"
            )
        try:
            text = _http_get(url, self._timeout)
        except OSError as exc:
            raise SourceReadError(f"failed to fetch source from {url}: {exc}") from exc
        return _as_dict(json.loads(text), source=url)

    def _load_file(self, path: Path) -> dict[str, Any]:
        """Read a file from disk, auto-detecting JSON vs CSV by file extension.

        CSV files are converted to the same dict shape that JSON files provide
        so the downstream validation path is identical for both formats.
        """
        if not path.is_file():
            raise SourceReadError(f"source file not found: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".csv":
            return _parse_csv(text, self.list_key)
        try:
            return _as_dict(json.loads(text), source=str(path))
        except json.JSONDecodeError as exc:
            raise SourceReadError(f"source file is not valid JSON: {path}: {exc}") from exc


class EnvironmentSourceReader(_FileApiSourceReader):
    """Reads an environment snapshot (FR-3)."""

    tool_name = "environment_source"
    model = EnvironmentInput
    list_key = "components"


class DependencySourceReader(_FileApiSourceReader):
    """Reads a dependency snapshot (FR-5)."""

    tool_name = "dependency_source"
    model = DependencyInput
    list_key = "dependencies"


class OperationalSourceReader(_FileApiSourceReader):
    """Reads a deployment-readiness snapshot (ADR-0016)."""

    tool_name = "operational_source"
    model = OperationalInput
    # Operational data is a top-level JSON object, not a list — list_key is unused
    # but required by the base class; any non-CSV read goes through the dict path.
    list_key = "operational"


class SecuritySourceReader(_FileApiSourceReader):
    """Reads a security and compliance posture snapshot (ADR-0016, gate-only dimension)."""

    tool_name = "security_source"
    model = SecurityInput
    # Security data is a top-level JSON object, not a list — list_key is unused
    # but required by the base class; any non-CSV read goes through the dict path.
    list_key = "security"


class PerformanceSourceReader(_FileApiSourceReader):
    """Reads a performance and NFR posture snapshot (ADR-0016, gate-only dimension)."""

    tool_name = "performance_source"
    model = PerformanceInput
    # Performance data is a top-level JSON object, not a list — list_key is unused
    # but required by the base class; any non-CSV read goes through the dict path.
    list_key = "performance"


class OperabilitySourceReader(_FileApiSourceReader):
    """Reads a deployment-operability snapshot (ADR-0016 item 7, weighted 0.07)."""

    tool_name = "operability_source"
    model = OperabilityInput
    # Operability data is a top-level JSON object — list_key unused for non-CSV reads.
    list_key = "operability"


class ObservabilitySourceReader(_FileApiSourceReader):
    """Reads a monitoring/alerting coverage snapshot (ADR-0016 item 7, weighted 0.03)."""

    tool_name = "observability_source"
    model = ObservabilityInput
    # Observability data is a top-level JSON object — list_key unused for non-CSV reads.
    list_key = "observability"


class RollbackSourceReader(_FileApiSourceReader):
    """Reads a rollback-plan posture snapshot (ADR-0016 item 7, gate-only)."""

    tool_name = "rollback_source"
    model = RollbackInput
    # Rollback data is a top-level JSON object — list_key unused for non-CSV reads.
    list_key = "rollback"


class AccessibilitySourceReader(_FileApiSourceReader):
    """Reads a WCAG accessibility compliance posture snapshot (ADR-0016 item 8, gate-only)."""

    tool_name = "accessibility_source"
    model = AccessibilityInput
    list_key = "accessibility"


class AuditabilitySourceReader(_FileApiSourceReader):
    """Reads an audit-trail completeness posture snapshot (ADR-0016 item 9, gate-only)."""

    tool_name = "auditability_source"
    model = AuditabilityInput
    list_key = "auditability"


class DisasterRecoverySourceReader(_FileApiSourceReader):
    """Reads a disaster recovery plan and test-evidence snapshot (ADR-0016 item 10, gate-only)."""

    tool_name = "disaster_recovery_source"
    model = DisasterRecoveryInput
    list_key = "disaster_recovery"


class DataReconciliationSourceReader(_FileApiSourceReader):
    """Reads a data migration reconciliation posture snapshot (ADR-0016 item 11, gate-only)."""

    tool_name = "data_reconciliation_source"
    model = DataReconciliationInput
    list_key = "data_reconciliation"


class FailureModeSourceReader(_FileApiSourceReader):
    """Reads a resilience and failure-mode posture snapshot (ADR-0016 item 12, gate-only)."""

    tool_name = "failure_mode_source"
    model = FailureModeInput
    list_key = "failure_mode"


class DependencyRiskSourceReader(_FileApiSourceReader):
    """Reads a software supply-chain risk posture snapshot (ADR-0016 item 13, gate-only)."""

    tool_name = "dependency_risk_source"
    model = DependencyRiskInput
    list_key = "dependency_risk"


class ProductionReadinessSourceReader(_FileApiSourceReader):
    """Reads a go-live readiness checklist snapshot (ADR-0016 item 14, gate-only)."""

    tool_name = "production_readiness_source"
    model = ProductionReadinessInput
    list_key = "production_readiness"


class ArchitectureFitnessSourceReader(_FileApiSourceReader):
    """Reads an architecture fitness function scan result (ADR-0016 item 15, gate-only)."""

    tool_name = "architecture_fitness_source"
    model = ArchitectureFitnessInput
    list_key = "architecture_fitness"


class ArchitectureDriftSourceReader(_FileApiSourceReader):
    """Reads an architecture baseline drift assessment (ADR-0016 item 16, gate-only)."""

    tool_name = "architecture_drift_source"
    model = ArchitectureDriftInput
    list_key = "architecture_drift"
