"""Composition root — wire config + tools + assessors + orchestrator into one run.

``assess()`` is the single entry point the CLI (and tests, and a future API) call:
given a validated config and a release id, it builds the source readers, the
assessors, and the orchestrator, then returns the ``AssessmentOutputModel``.

Provider selection honors ``config.provider.type``:
- ``rule_based``: deterministic, no model, always available (default)
- ``local_llm``: Ollama on 127.0.0.1 — requires ``provider.local_llm`` config block
- ``mock_llm``: fixture-backed demo provider — requires ``provider.mock_llm.fixture_dir``
- ``bedrock``: Amazon Bedrock Converse API (Phase 2) — requires ``provider.bedrock`` block
- ``claude``: Anthropic Messages API (Phase 2) — requires ``provider.claude`` block
  and ``ANTHROPIC_API_KEY`` environment variable

Core assessors (always wired): Scope, Estimation, TestReadiness, Environment,
Dependency, Operability (ADR-0016 item 7 — replaces Operational).
Opt-in assessors: ObservabilityAssessor (weighted 0.03), RollbackAssessor,
SecurityComplianceAssessor, PerformanceAssessor (items 2-3, 7), and the nine
gate-only assessors from ADR-0016 items 8-16 (Accessibility, Auditability,
DisasterRecovery, DataReconciliation, FailureMode, DependencyRisk,
ProductionReadiness, ArchitectureFitness, ArchitectureDrift).
All opt-in assessors are wired only when their respective source is configured.
"""

from __future__ import annotations

from rrr.assessors import (
    AccessibilityAssessor,
    ArchitectureDriftAssessor,
    ArchitectureFitnessAssessor,
    AuditabilityAssessor,
    DataReconciliationAssessor,
    DependencyAssessor,
    DependencyRiskAssessor,
    DisasterRecoveryAssessor,
    EnvironmentAssessor,
    EstimationAssessor,
    FailureModeAssessor,
    ObservabilityAssessor,
    OperabilityAssessor,
    PerformanceAssessor,
    ProductionReadinessAssessor,
    RollbackAssessor,
    ScopeAssessor,
    SecurityComplianceAssessor,
    TestReadinessAssessor,
)
from rrr.assessors.base import BaseAssessor
from rrr.config.schema import FileSource, ProviderType, RRRConfig
from rrr.errors import ConfigurationError
from rrr.memory import AbstractAssessmentStore, SQLiteAssessmentStore
from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import ReleaseRiskTier
from rrr.orchestration import compute_trends, run_assessment_graph
from rrr.providers.base import LLMProvider
from rrr.providers.rule_based import RuleBasedProvider
from rrr.tools import (
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
    PerformanceSourceReader,
    ProductionReadinessSourceReader,
    RKTBrainReader,
    RollbackSourceReader,
    SecuritySourceReader,
    ToolRunner,
)


def build_provider(config: RRRConfig) -> LLMProvider:
    """Select the LLM provider from config (ADR-0006, ADR-0010)."""
    if config.provider.type is ProviderType.RULE_BASED:
        return RuleBasedProvider()
    if config.provider.type is ProviderType.LOCAL_LLM:
        from rrr.providers.local_llm import LocalLLMProvider

        if config.provider.local_llm is None:
            raise ConfigurationError(
                "provider.type is 'local_llm' but the [provider.local_llm] config block "
                "is missing — add endpoint and model (e.g. endpoint: http://127.0.0.1:11434, "
                "model: llama3)"
            )
        return LocalLLMProvider(
            endpoint=config.provider.local_llm.endpoint,
            model=config.provider.local_llm.model,
            allowed_hosts=tuple(config.sources.allowed_hosts),
            timeout=float(config.timeouts.external_source),
            repair_retries=config.provider.repair_retries,
        )
    if config.provider.type is ProviderType.MOCK_LLM:
        from rrr.providers.mock_llm import MockLLMProvider

        if config.provider.mock_llm is None:
            raise ConfigurationError(
                "provider.type is 'mock_llm' but the [provider.mock_llm] config block "
                "is missing — add fixture_dir (e.g. fixture_dir: tests/fixtures/llm_responses)"
            )
        return MockLLMProvider(
            fixture_dir=config.provider.mock_llm.fixture_dir,
            repair_retries=config.provider.repair_retries,
        )
    if config.provider.type is ProviderType.BEDROCK:
        from rrr.providers.bedrock import BedrockProvider

        if config.provider.bedrock is None:
            raise ConfigurationError(
                "provider.type is 'bedrock' but the [provider.bedrock] config block "
                "is missing — add at minimum: model_id and region (ADR-0019)"
            )
        bc = config.provider.bedrock
        return BedrockProvider(
            model_id=bc.model_id,
            region=bc.region,
            max_tokens=bc.max_tokens,
            temperature=bc.temperature,
            repair_retries=config.provider.repair_retries,
        )
    if config.provider.type is ProviderType.CLAUDE:
        from rrr.providers.claude import ClaudeProvider

        if config.provider.claude is None:
            raise ConfigurationError(
                "provider.type is 'claude' but the [provider.claude] config block "
                "is missing — add at minimum: model (ADR-0006)"
            )
        cc = config.provider.claude
        return ClaudeProvider(
            model=cc.model,
            max_tokens=cc.max_tokens,
            temperature=cc.temperature,
            repair_retries=config.provider.repair_retries,
        )
    raise ConfigurationError(
        f"provider.type {config.provider.type.value!r} is not recognised; "
        f"valid values: rule_based, local_llm, mock_llm, bedrock, claude"
    )


def build_store(config: RRRConfig) -> AbstractAssessmentStore:
    """Instantiate the SQLite assessment store with optional Chroma RAG (FR-14, ADR-0003/0007)."""
    return SQLiteAssessmentStore(
        config.memory.sqlite_path,
        retry_attempts=config.persistence.retry_attempts,
        retry_interval=config.persistence.retry_interval_seconds,
        chroma_path=config.memory.chroma_path if config.memory.chroma_path else None,
    )


def assess(
    config: RRRConfig,
    *,
    release: str,
    value_stream: str | None = None,
    snapshot: str | None = None,
    tier: ReleaseRiskTier | None = None,
    _provider: LLMProvider | None = None,
) -> AssessmentOutputModel:
    """Assess one release and return the full result.

    ``snapshot`` overrides ``config.sources.brain.snapshot`` so callers can score
    a specific historical brain date without rebuilding the config object — used by
    the Trends panel to compute scores across all weekly snapshots in one pass.

    ``tier`` selects a release risk tier threshold set (ADR-0016 items 4-5). When
    None, the global thresholds in config are used. The tier label is recorded in
    the output ``AssessmentOutputModel.tier``.

    ``_provider`` is an internal escape hatch for bulk historical scoring: pass a
    pre-built ``RuleBasedProvider`` to avoid any LLM or network calls during
    batch computation.
    """
    vs = value_stream or config.sources.brain.value_stream
    snapshot = snapshot if snapshot is not None else config.sources.brain.snapshot
    provider = _provider if _provider is not None else build_provider(config)
    runner = ToolRunner(
        default_timeout=float(config.timeouts.tool_default),
        retry_count=config.tools.retry_count,
        retry_backoff_s=config.tools.retry_backoff_s,
    )
    brain = RKTBrainReader(config.sources.brain.dir)
    tr_weights = config.assessors.test_readiness.weights

    assessors: list[BaseAssessor] = [
        ScopeAssessor(
            runner,
            provider,
            brain,
            value_stream=vs,
            snapshot=snapshot,
            ir_name=release,
            scope_creep_threshold=config.gates.scope_creep_threshold,
        ),
        EstimationAssessor(
            runner,
            provider,
            brain,
            value_stream=vs,
            snapshot=snapshot,
            ir_name=release,
        ),
        TestReadinessAssessor(
            runner,
            provider,
            brain,
            value_stream=vs,
            snapshot=snapshot,
            ir_name=release,
            quality_weight=tr_weights["quality"],
            defect_weight=tr_weights["defect_trend"],
            e2e_weight=tr_weights["e2e_pass_rate"],
            e2e_critical_floor=config.gates.e2e_critical_floor,
            freshness_max_age_days=config.assessors.test_readiness.freshness_max_age_days,
        ),
        EnvironmentAssessor(runner, provider, _environment_reader(config)),
        DependencyAssessor(runner, provider, _dependency_reader(config)),
        OperabilityAssessor(runner, provider, _operability_reader(config)),
    ]
    # Observability is opt-in (weighted 0.03) — wired when source is configured (ADR-0016 item 7).
    if config.sources.observability is not None:
        assessors.append(ObservabilityAssessor(runner, provider, _observability_reader(config)))
    # Rollback is opt-in gate-only — wired when source is configured (ADR-0016 item 7).
    if config.sources.rollback is not None:
        assessors.append(RollbackAssessor(runner, provider, _rollback_reader(config)))
    # Security dimension is opt-in — only wired when the source is configured (ADR-0016 item 2).
    if config.sources.security is not None:
        assessors.append(
            SecurityComplianceAssessor(
                runner,
                provider,
                _security_reader(config),
                config.assessors.security,
            )
        )
    # Performance dimension is opt-in — only wired when the source is configured (ADR-0016 item 3).
    if config.sources.performance is not None:
        assessors.append(
            PerformanceAssessor(
                runner,
                provider,
                _performance_reader(config),
                config.assessors.performance,
            )
        )
    # Gate-only dimensions — ADR-0016 items 8-16; all opt-in via sources config.
    if config.sources.accessibility is not None:
        assessors.append(
            AccessibilityAssessor(runner, provider, _accessibility_reader(config))
        )
    if config.sources.auditability is not None:
        assessors.append(
            AuditabilityAssessor(runner, provider, _auditability_reader(config))
        )
    if config.sources.disaster_recovery is not None:
        assessors.append(
            DisasterRecoveryAssessor(runner, provider, _disaster_recovery_reader(config))
        )
    if config.sources.data_reconciliation is not None:
        assessors.append(
            DataReconciliationAssessor(runner, provider, _data_reconciliation_reader(config))
        )
    if config.sources.failure_mode is not None:
        assessors.append(
            FailureModeAssessor(runner, provider, _failure_mode_reader(config))
        )
    if config.sources.dependency_risk is not None:
        assessors.append(
            DependencyRiskAssessor(runner, provider, _dependency_risk_reader(config))
        )
    if config.sources.production_readiness is not None:
        assessors.append(
            ProductionReadinessAssessor(runner, provider, _production_readiness_reader(config))
        )
    if config.sources.architecture_fitness is not None:
        assessors.append(
            ArchitectureFitnessAssessor(runner, provider, _architecture_fitness_reader(config))
        )
    if config.sources.architecture_drift is not None:
        assessors.append(
            ArchitectureDriftAssessor(runner, provider, _architecture_drift_reader(config))
        )
    return run_assessment_graph(
        config, assessors, release=release, value_stream=vs, provider=provider, tier=tier
    )


def run_and_record(
    config: RRRConfig,
    *,
    release: str,
    value_stream: str | None = None,
    tier: ReleaseRiskTier | None = None,
    store: AbstractAssessmentStore | None = None,
) -> AssessmentOutputModel:
    """Assess, attach trends vs the previous run (FR-9), persist (FR-14), and return.

    The pure :func:`assess` does the compute; this adds the stateful concerns
    (history lookup, trend computation, persistence). Pass ``store`` to inject a
    pre-built store (useful in tests and the UI); omit to have ``build_store``
    create one from ``config.memory.backend``.

    ``tier`` is threaded to :func:`assess` unchanged — see that function for details.
    """
    result = assess(config, release=release, value_stream=value_stream, tier=tier)
    owns_store = store is None
    store = store if store is not None else build_store(config)
    try:
        previous = store.latest_for(result.release, result.value_stream)
        trends = compute_trends(result, previous, config.trend)
        if trends:
            result = result.model_copy(update={"trend_data": trends})
        store.save(result)
    finally:
        if owns_store:
            store.close()
    return result


def _environment_reader(config: RRRConfig) -> EnvironmentSourceReader:
    """Build an EnvironmentSourceReader from whichever source type is configured.

    The source is either a local file (JSON or CSV, ``type: file``) or a
    localhost API endpoint (``type: api``). For API sources the allow-list and
    timeout come from config so local-first is guaranteed end-to-end (ADR-0010).
    """
    src = config.sources.environment
    if isinstance(src, FileSource):
        return EnvironmentSourceReader(path=src.path)
    return EnvironmentSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _dependency_reader(config: RRRConfig) -> DependencySourceReader:
    """Build a DependencySourceReader from whichever source type is configured.

    Same file-or-API choice as the environment reader. Both helpers exist to
    keep the main ``assess()`` function readable — each reader has its own
    config block but the construction logic is identical so it's factored out.
    """
    src = config.sources.dependency
    if isinstance(src, FileSource):
        return DependencySourceReader(path=src.path)
    return DependencySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _operability_reader(config: RRRConfig) -> OperabilitySourceReader:
    """Build an OperabilitySourceReader from whichever source type is configured.

    Replaces the old ``_operational_reader`` (ADR-0016 item 7 split). The
    operability data covers deployment pipeline health and day-2 ops readiness.
    """
    src = config.sources.operability
    if isinstance(src, FileSource):
        return OperabilitySourceReader(path=src.path)
    return OperabilitySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _observability_reader(config: RRRConfig) -> ObservabilitySourceReader:
    """Build an ObservabilitySourceReader from whichever source type is configured.

    Called only when ``config.sources.observability`` is not None. Observability
    data covers monitoring dashboards, SLO alerting, and trace/log coverage.
    """
    src = config.sources.observability
    assert src is not None  # caller guarantees this via the opt-in guard in assess()
    if isinstance(src, FileSource):
        return ObservabilitySourceReader(path=src.path)
    return ObservabilitySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _rollback_reader(config: RRRConfig) -> RollbackSourceReader:
    """Build a RollbackSourceReader from whichever source type is configured.

    Called only when ``config.sources.rollback`` is not None. Rollback data
    covers plan completeness, test evidence, and data-rollback coverage.
    """
    src = config.sources.rollback
    assert src is not None  # caller guarantees this via the opt-in guard in assess()
    if isinstance(src, FileSource):
        return RollbackSourceReader(path=src.path)
    return RollbackSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _security_reader(config: RRRConfig) -> SecuritySourceReader:
    """Build a SecuritySourceReader from whichever source type is configured.

    Called only when ``config.sources.security`` is not None. The security
    posture data comes from the security toolchain (SAST/DAST scanners, CVE
    registries), not from the RKT brain extract (ADR-0016, gate-only dimension).
    """
    src = config.sources.security
    assert src is not None  # caller guarantees this; checked by the opt-in guard in assess()
    if isinstance(src, FileSource):
        return SecuritySourceReader(path=src.path)
    return SecuritySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _performance_reader(config: RRRConfig) -> PerformanceSourceReader:
    """Build a PerformanceSourceReader from whichever source type is configured.

    Called only when ``config.sources.performance`` is not None. The performance
    data comes from load runners and APM tooling, not from the RKT brain extract
    (ADR-0016, gate-only dimension).
    """
    src = config.sources.performance
    assert src is not None  # caller guarantees this; checked by the opt-in guard in assess()
    if isinstance(src, FileSource):
        return PerformanceSourceReader(path=src.path)
    return PerformanceSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _accessibility_reader(config: RRRConfig) -> AccessibilitySourceReader:
    """Build an AccessibilitySourceReader from the configured source (ADR-0016 item 8)."""
    src = config.sources.accessibility
    assert src is not None
    if isinstance(src, FileSource):
        return AccessibilitySourceReader(path=src.path)
    return AccessibilitySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _auditability_reader(config: RRRConfig) -> AuditabilitySourceReader:
    """Build an AuditabilitySourceReader from the configured source (ADR-0016 item 9)."""
    src = config.sources.auditability
    assert src is not None
    if isinstance(src, FileSource):
        return AuditabilitySourceReader(path=src.path)
    return AuditabilitySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _disaster_recovery_reader(config: RRRConfig) -> DisasterRecoverySourceReader:
    """Build a DisasterRecoverySourceReader from the configured source (ADR-0016 item 10)."""
    src = config.sources.disaster_recovery
    assert src is not None
    if isinstance(src, FileSource):
        return DisasterRecoverySourceReader(path=src.path)
    return DisasterRecoverySourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _data_reconciliation_reader(config: RRRConfig) -> DataReconciliationSourceReader:
    """Build a DataReconciliationSourceReader from the configured source (ADR-0016 item 11)."""
    src = config.sources.data_reconciliation
    assert src is not None
    if isinstance(src, FileSource):
        return DataReconciliationSourceReader(path=src.path)
    return DataReconciliationSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _failure_mode_reader(config: RRRConfig) -> FailureModeSourceReader:
    """Build a FailureModeSourceReader from the configured source (ADR-0016 item 12)."""
    src = config.sources.failure_mode
    assert src is not None
    if isinstance(src, FileSource):
        return FailureModeSourceReader(path=src.path)
    return FailureModeSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _dependency_risk_reader(config: RRRConfig) -> DependencyRiskSourceReader:
    """Build a DependencyRiskSourceReader from the configured source (ADR-0016 item 13)."""
    src = config.sources.dependency_risk
    assert src is not None
    if isinstance(src, FileSource):
        return DependencyRiskSourceReader(path=src.path)
    return DependencyRiskSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _production_readiness_reader(config: RRRConfig) -> ProductionReadinessSourceReader:
    """Build a ProductionReadinessSourceReader from the configured source (ADR-0016 item 14)."""
    src = config.sources.production_readiness
    assert src is not None
    if isinstance(src, FileSource):
        return ProductionReadinessSourceReader(path=src.path)
    return ProductionReadinessSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _architecture_fitness_reader(config: RRRConfig) -> ArchitectureFitnessSourceReader:
    """Build an ArchitectureFitnessSourceReader from the configured source (ADR-0016 item 15)."""
    src = config.sources.architecture_fitness
    assert src is not None
    if isinstance(src, FileSource):
        return ArchitectureFitnessSourceReader(path=src.path)
    return ArchitectureFitnessSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )


def _architecture_drift_reader(config: RRRConfig) -> ArchitectureDriftSourceReader:
    """Build an ArchitectureDriftSourceReader from the configured source (ADR-0016 item 16)."""
    src = config.sources.architecture_drift
    assert src is not None
    if isinstance(src, FileSource):
        return ArchitectureDriftSourceReader(path=src.path)
    return ArchitectureDriftSourceReader(
        url=src.url,
        allowed_hosts=tuple(config.sources.allowed_hosts),
        timeout=float(config.timeouts.external_source),
    )
