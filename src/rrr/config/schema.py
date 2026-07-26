"""Pydantic config schema — validates ``default_config.yaml`` merged with overrides (FR-15).

Mirrors the YAML structure one-to-one. Reuses the strict, frozen :class:`RRRModel`
posture so a misspelled config key (``extra="forbid"``) or an out-of-range value
fails loudly at load time rather than surfacing as a confusing runtime bug.

Local-first is enforced here (NFR-8 / ADR-0010): any ``api`` data source must
resolve to an allow-listed host, checked during validation — before any network
call is ever attempted.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, PositiveInt, field_validator, model_validator

from rrr.models.base import RRRModel
from rrr.models.enums import DimensionName, ReleaseRiskTier, Verdict

WEIGHT_SUM_TOLERANCE = 1e-6
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Gate caps may only *lower* a verdict; GO/INCOMPLETE are not valid ceilings (ADR-0013).
_VALID_CAPS = {Verdict.NO_GO, Verdict.CONDITIONAL}


class ProviderType(StrEnum):
    """Which LLM provider the pipeline uses for narrative and verdict reasoning."""

    RULE_BASED = "rule_based"
    LOCAL_LLM = "local_llm"
    # Fixture-backed demo provider — shows AI reasoning without a running model (Phase 1).
    MOCK_LLM = "mock_llm"
    CLAUDE = "claude"
    # Phase 2 — external AWS Bedrock call (ADR-0019). Breaks ADR-0010 local-first by design.
    BEDROCK = "bedrock"


class WeightsConfig(RRRModel):
    """Dimension weights; must sum to 1.0 (FR-15, ADR-0011, ADR-0016 item 7).

    OPERABILITY (0.07) + OBSERVABILITY (0.03) replace the old OPERATIONAL (0.10)
    following the ADR-0016 item-7 split. OBSERVABILITY is opt-in; when absent its
    weight is redistributed by the scoring engine (ADR-0005).
    """

    test_readiness: float = Field(ge=0.0, le=1.0)
    scope: float = Field(ge=0.0, le=1.0)
    environment: float = Field(ge=0.0, le=1.0)
    dependency: float = Field(ge=0.0, le=1.0)
    estimation: float = Field(ge=0.0, le=1.0)
    operability: float = Field(ge=0.0, le=1.0)
    observability: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> WeightsConfig:
        """Reject any weight set that does not add up to 1.0 (within floating-point tolerance).

        The scoring formula multiplies each dimension score by its weight — if
        weights don't sum to 1.0 the final score would be on a different scale
        than the GO/NO_GO thresholds, producing wrong verdicts silently.
        """
        total = (
            self.test_readiness
            + self.scope
            + self.environment
            + self.dependency
            + self.estimation
            + self.operability
            + self.observability
        )
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"dimension weights must sum to 1.0, got {total:.6f}")
        return self


class ThresholdsConfig(RRRModel):
    """Verdict score bands and robustness guards (FR-8, ADR-0015)."""

    go: float = Field(gt=0.0, le=1.0)
    no_go: float = Field(ge=0.0, lt=1.0)
    minimum_assessors: PositiveInt
    required_dimensions: list[DimensionName] = Field(
        default_factory=lambda: [DimensionName.TEST_READINESS, DimensionName.ENVIRONMENT],
        description="Dimensions that must be available for a GO verdict (ADR-0015).",
    )
    confidence_floor: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="GO capped to CONDITIONAL if aggregate confidence falls below this (ADR-0015).",
    )

    @model_validator(mode="after")
    def _go_above_no_go(self) -> ThresholdsConfig:
        if self.go <= self.no_go:
            raise ValueError(
                f"thresholds.go ({self.go}) must be greater than thresholds.no_go ({self.no_go})"
            )
        return self


class TierThresholds(RRRModel):
    """Threshold overrides for one release risk tier (ADR-0016 items 4-5).

    When the ``--tier`` flag is active, these values override the global
    ``ThresholdsConfig`` for the fields they cover. ``excluded_gate_dims``
    lists gate-only dimensions whose risk factors are suppressed for this tier
    (e.g. ACCESSIBILITY excluded for HOTFIX releases where it is not applicable).
    """

    go: float = Field(
        gt=0.0,
        le=1.0,
        description="Minimum score for a GO verdict under this tier.",
    )
    no_go: float = Field(
        ge=0.0,
        lt=1.0,
        description="Score below which NO_GO is the band verdict under this tier.",
    )
    confidence_floor: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="GO → CONDITIONAL if aggregate confidence falls below this (ADR-0015).",
    )
    required_gate_dims: list[DimensionName] = Field(
        default_factory=list,
        description="Dimensions that must be available for a GO verdict under this tier.",
    )
    excluded_gate_dims: list[DimensionName] = Field(
        default_factory=list,
        description=(
            "Gate-only dimensions whose risk factors are ignored for this tier. "
            "Allows hotfix releases to bypass non-applicable gates (e.g. ACCESSIBILITY)."
        ),
    )

    @model_validator(mode="after")
    def _go_above_no_go(self) -> TierThresholds:
        """Reject any tier threshold set where go <= no_go.

        The band between no_go and go is the CONDITIONAL zone; if they cross
        there is no CONDITIONAL band and the verdicts would be incorrect.
        """
        if self.go <= self.no_go:
            raise ValueError(
                f"tier thresholds: go ({self.go}) must be greater than no_go ({self.no_go})"
            )
        return self


class TiersConfig(RRRModel):
    """Named threshold sets for HOTFIX, STANDARD, and MAJOR risk tiers (ADR-0016 items 4-5).

    Each tier defines relaxed (HOTFIX) or stricter (MAJOR) score thresholds,
    required gate dimensions, and an optional list of gate-only dimensions to
    exclude (so a hotfix release is not blocked by gates irrelevant to small fixes).
    """

    hotfix: TierThresholds = Field(
        description="Relaxed thresholds for small targeted fixes — minimal required dims.",
    )
    standard: TierThresholds = Field(
        description="Default thresholds for regular feature releases.",
    )
    major: TierThresholds = Field(
        description="Strict thresholds for large or high-risk releases.",
    )

    def for_tier(self, tier: ReleaseRiskTier) -> TierThresholds:
        """Return the TierThresholds for the given tier."""
        result: TierThresholds = getattr(self, tier.value)
        return result


class TrendConfig(RRRModel):
    """Per-dimension trend deltas vs previous assessment (FR-9)."""

    improving_delta: float = Field(gt=0.0)
    degrading_delta: float = Field(lt=0.0)


class GatesConfig(RRRModel):
    """Verdict veto/cap gates (ADR-0013). Cap fields may only be NO_GO or CONDITIONAL."""

    enabled: bool = True
    e2e_critical_floor: float = Field(ge=0.0, le=1.0)
    blocker_defects: Verdict
    critical_defects_limit: int = Field(ge=0)
    environment_down: Verdict
    environment_degraded: Verdict
    dependency_failed: Verdict
    dependency_blocking: Verdict
    scope_creep_threshold: float = Field(ge=0.0)

    @field_validator(
        "blocker_defects",
        "environment_down",
        "dependency_failed",
        "environment_degraded",
        "dependency_blocking",
    )
    @classmethod
    def _cap_is_restrictive(cls, v: Verdict) -> Verdict:
        if v not in _VALID_CAPS:
            raise ValueError(f"gate cap must be one of {{NO_GO, CONDITIONAL}}, got {v.value}")
        return v


class TimeoutsConfig(RRRModel):
    """Execution timeouts in seconds (NFR-1, FR-11)."""

    assessor_default: PositiveInt
    environment_source: PositiveInt
    external_source: PositiveInt
    tool_default: PositiveInt


class PersistenceConfig(RRRModel):
    """SQLite persist retry policy (FR-14)."""

    retry_attempts: int = Field(ge=0)
    retry_interval_seconds: float = Field(ge=0.0)


class ToolsConfig(RRRModel):
    """Tool invocation retry policy for transient failures (NFR-1, W6).

    Applies only to ``ToolInvocationError``; ``ToolTimeoutError`` is never
    retried — a second attempt would likely time out again and double the
    latency penalty on an already-slow assessor.
    """

    retry_count: int = Field(
        default=1,
        ge=0,
        description="Extra attempts on ToolInvocationError (0 = no retry).",
    )
    retry_backoff_s: float = Field(
        default=0.5,
        ge=0.0,
        description="Seconds to wait between attempts.",
    )


class LocalLLMConfig(RRRModel):
    """Opt-in on-machine LLM (Ollama/llama.cpp on 127.0.0.1)."""

    endpoint: str
    model: str


class MockLLMConfig(RRRModel):
    """Fixture-backed demo provider config (Phase 1 only)."""

    fixture_dir: str


class ClaudeConfig(RRRModel):
    """Anthropic API provider settings (Phase 2, ADR-0006).

    The API key is intentionally absent here — pass it via the ``ANTHROPIC_API_KEY``
    environment variable so it never lands in a config file or source tree.
    """

    model: str = Field(
        default="claude-opus-4-8",
        description="Anthropic model ID — e.g. 'claude-opus-4-8' or 'claude-sonnet-4-6'.",
    )
    max_tokens: int = Field(default=1024, ge=1, description="Maximum output tokens per call.")
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature — keep low for structured JSON output.",
    )


class BedrockConfig(RRRModel):
    """Amazon Bedrock Converse API provider settings (Phase 2, ADR-0019)."""

    model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        description="Bedrock modelId — any model available in your account.",
    )
    region: str = Field(default="us-east-1", description="AWS region for the Bedrock endpoint.")
    max_tokens: int = Field(default=1024, ge=1, description="Maximum output tokens per call.")
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature — keep low for structured JSON output.",
    )


class ProviderConfig(RRRModel):
    """LLM provider selection (ADR-0006, FR-30)."""

    type: ProviderType = ProviderType.RULE_BASED
    repair_retries: int = Field(default=1, ge=0)
    local_llm: LocalLLMConfig | None = None
    mock_llm: MockLLMConfig | None = None
    claude: ClaudeConfig | None = None
    bedrock: BedrockConfig | None = None


class BrainSourceConfig(RRRModel):
    """Brain extract location/selection (ADR-0012)."""

    dir: str
    value_stream: str
    snapshot: str = "latest"

    @field_validator("snapshot")
    @classmethod
    def _snapshot_form(cls, v: str) -> str:
        """Accept 'latest' or a strict YYYY-MM-DD date; reject anything else.

        The brain reader sorts snapshot directories by name — ISO date strings
        sort correctly as plain strings, so this format is load-bearing for the
        'latest' selection logic in RKTBrainReader._select_snapshot().
        """
        if v == "latest":
            return v
        if not _ISO_DATE.match(v):
            raise ValueError(f"snapshot must be 'latest' or an ISO date YYYY-MM-DD, got {v!r}")
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"snapshot is not a valid date: {v!r}") from exc
        return v


class FileSource(RRRModel):
    """File-backed env/dependency source (FR-3 / FR-5)."""

    type: Literal["file"] = "file"
    path: str


class ApiSource(RRRModel):
    """Localhost-API env/dependency source. Host allow-listing is enforced by SourcesConfig."""

    type: Literal["api"]
    url: str


DataSource = Annotated[FileSource | ApiSource, Field(discriminator="type")]


class TestReadinessAssessorConfig(RRRModel):
    """Test Readiness sub-weights, E2E-absent policy, and data-freshness guard (FR-4, ADR-0012).

    ``freshness_max_age_days`` controls the input-freshness check: if the brain snapshot is
    older than this many days a MINOR risk factor is appended. Set to 0 to disable the check.
    """

    suite_pass_threshold: float = Field(ge=0.0, le=1.0)
    weights: dict[str, float]
    e2e_absent: Literal["renormalize", "drop", "zero"] = "renormalize"
    freshness_max_age_days: int = Field(
        default=30,
        ge=0,
        description="Warn when brain snapshot is older than this many days (0 = disabled).",
    )

    @field_validator("weights")
    @classmethod
    def _subweights_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        """Reject test-readiness sub-weights that don't add up to 1.0.

        The sub-weights (quality, defect_trend, e2e_pass_rate) are multiplied
        together inside TestReadinessAssessor to produce a single score. If they
        don't sum to 1.0 the assessor's combined score would not be on a [0,1]
        scale, breaking the top-level weighted average.
        """
        total = sum(v.values())
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"test_readiness sub-weights must sum to 1.0, got {total:.6f}")
        return v


class SecurityAssessorConfig(RRRModel):
    """Security & Compliance assessor tuning (ADR-0016, gate-only dimension).

    ``high_cve_threshold`` sets the minimum open high-severity CVE count that
    triggers a MAJOR risk factor. Below the threshold the dimension stays amber
    but without a verdict cap — above it the GateEngine applies CONDITIONAL.
    """

    high_cve_threshold: int = Field(
        default=5,
        ge=0,
        description="Open high-severity CVE count that triggers a MAJOR risk factor.",
    )


class PerformanceAssessorConfig(RRRModel):
    """Performance / NFR assessor tuning (ADR-0016, gate-only dimension).

    ``low_capacity_threshold_pct`` is the minimum acceptable capacity headroom;
    falling below it triggers a MAJOR risk factor (→ CONDITIONAL cap).

    ``slo_critical_multiplier`` controls when a latency breach escalates from
    MAJOR to CRITICAL: if observed P99 latency exceeds the SLO threshold by this
    multiple the GateEngine applies a NO_GO cap instead of CONDITIONAL.
    """

    low_capacity_threshold_pct: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description=(
            "Capacity headroom percentage below which a MAJOR risk factor is raised. "
            "Default 20 % — less than one-fifth of headroom remaining is high-risk."
        ),
    )
    slo_critical_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description=(
            "Ratio of observed P99 latency to the SLO threshold that escalates a "
            "latency breach from MAJOR to CRITICAL. Default 2.0 — twice the SLO."
        ),
    )


class AssessorsConfig(RRRModel):
    """Assessor-specific tuning."""

    test_readiness: TestReadinessAssessorConfig
    security: SecurityAssessorConfig = Field(default_factory=SecurityAssessorConfig)
    performance: PerformanceAssessorConfig = Field(default_factory=PerformanceAssessorConfig)


class SourcesConfig(RRRModel):
    """Input source wiring + local-first allow-list (NFR-8 / ADR-0010).

    OPERABILITY replaces the old OPERATIONAL source (ADR-0016 item 7 split).
    All other new fields (OBSERVABILITY, ROLLBACK, SECURITY, PERFORMANCE, and the
    nine ADR-0016 items 8-16 gate-only assessors) are opt-in: each assessor is
    wired into the pipeline only when its source is configured.
    """

    brain: BrainSourceConfig
    environment: DataSource
    dependency: DataSource
    operability: DataSource
    observability: DataSource | None = Field(
        default=None,
        description=(
            "Optional observability/monitoring source (ADR-0016 item 7). When absent "
            "the ObservabilityAssessor is not wired and its 0.03 weight redistributes."
        ),
    )
    rollback: DataSource | None = Field(
        default=None,
        description=(
            "Optional rollback-plan source (ADR-0016 item 7, gate-only). When absent "
            "the RollbackAssessor is not wired into the pipeline."
        ),
    )
    security: DataSource | None = Field(
        default=None,
        description=(
            "Optional security posture source (ADR-0016 item 2). When absent the "
            "SecurityComplianceAssessor is not wired into the pipeline."
        ),
    )
    performance: DataSource | None = Field(
        default=None,
        description=(
            "Optional performance / NFR source (ADR-0016 item 3). When absent the "
            "PerformanceAssessor is not wired into the pipeline."
        ),
    )
    # ADR-0016 items 8-16 — nine new gate-only dimensions, all opt-in.
    accessibility: DataSource | None = Field(
        default=None,
        description=(
            "Optional WCAG accessibility compliance source (ADR-0016 item 8). When absent "
            "the AccessibilityAssessor is not wired into the pipeline."
        ),
    )
    auditability: DataSource | None = Field(
        default=None,
        description=(
            "Optional audit-trail completeness source (ADR-0016 item 9). When absent "
            "the AuditabilityAssessor is not wired into the pipeline."
        ),
    )
    disaster_recovery: DataSource | None = Field(
        default=None,
        description=(
            "Optional disaster recovery plan and test-evidence source (ADR-0016 item 10). "
            "When absent the DisasterRecoveryAssessor is not wired into the pipeline."
        ),
    )
    data_reconciliation: DataSource | None = Field(
        default=None,
        description=(
            "Optional data migration reconciliation source (ADR-0016 item 11). When absent "
            "the DataReconciliationAssessor is not wired into the pipeline."
        ),
    )
    failure_mode: DataSource | None = Field(
        default=None,
        description=(
            "Optional resilience / failure-mode source (ADR-0016 item 12). When absent "
            "the FailureModeAssessor is not wired into the pipeline."
        ),
    )
    dependency_risk: DataSource | None = Field(
        default=None,
        description=(
            "Optional software supply-chain risk source (ADR-0016 item 13). When absent "
            "the DependencyRiskAssessor is not wired into the pipeline."
        ),
    )
    production_readiness: DataSource | None = Field(
        default=None,
        description=(
            "Optional go-live readiness checklist source (ADR-0016 item 14). When absent "
            "the ProductionReadinessAssessor is not wired into the pipeline."
        ),
    )
    architecture_fitness: DataSource | None = Field(
        default=None,
        description=(
            "Optional architecture fitness function scan source (ADR-0016 item 15). When absent "
            "the ArchitectureFitnessAssessor is not wired into the pipeline."
        ),
    )
    architecture_drift: DataSource | None = Field(
        default=None,
        description=(
            "Optional architecture baseline drift assessment source (ADR-0016 item 16). "
            "When absent the ArchitectureDriftAssessor is not wired into the pipeline."
        ),
    )
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])

    @model_validator(mode="after")
    def _api_hosts_allow_listed(self) -> SourcesConfig:
        """Reject any API source whose host is not on the allow-list (NFR-8, ADR-0010).

        Checked at config-load time so a mis-configured URL is caught before the
        pipeline starts, not mid-run when a source reader attempts the connection.
        """
        named_sources: list[tuple[str, DataSource | None]] = [
            ("environment", self.environment),
            ("dependency", self.dependency),
            ("operability", self.operability),
            ("observability", self.observability),
            ("rollback", self.rollback),
            ("security", self.security),
            ("performance", self.performance),
            ("accessibility", self.accessibility),
            ("auditability", self.auditability),
            ("disaster_recovery", self.disaster_recovery),
            ("data_reconciliation", self.data_reconciliation),
            ("failure_mode", self.failure_mode),
            ("dependency_risk", self.dependency_risk),
            ("production_readiness", self.production_readiness),
            ("architecture_fitness", self.architecture_fitness),
            ("architecture_drift", self.architecture_drift),
        ]
        for label, src in named_sources:
            if isinstance(src, ApiSource):
                host = urlparse(src.url).hostname
                if host not in self.allowed_hosts:
                    raise ValueError(
                        f"sources.{label} url host {host!r} is not allow-listed "
                        f"(allowed: {self.allowed_hosts}) — local-first, NFR-8/ADR-0010"
                    )
        return self


class MemoryConfig(RRRModel):
    """SQLite + Chroma paths and RAG retrieval depth (FR-24, ADR-0003/0007).

    ``chroma_path`` is optional. Setting it enables the vector index; leaving it
    empty or ``null`` disables RAG silently — all other pipeline behaviour is
    unaffected (Chroma is deferrable per ADR-0007).
    """

    sqlite_path: str
    chroma_path: str | None = Field(
        default=None,
        description="Directory for Chroma persistence. None disables the RAG index.",
    )
    rag_top_k: PositiveInt
    backend: Literal["sqlite"] = Field(
        default="sqlite",
        description="Storage backend. Only 'sqlite' (local file at sqlite_path) is supported.",
    )


class ValueStreamConfig(RRRModel):
    """Value-stream identity and alias registry for multi-name VS matching.

    Many programme artefacts reference the same value stream under different
    names (e.g. "OSM", "OS&M", "Offer Selection & Management").  This registry
    is the single source of truth used by the Trends tab to classify every
    release as *direct*, *dependency*, *supporting*, or *other* relative to the
    configured value stream.

    ``related_programmes`` lists supporting-system programme codes (e.g. AIMS,
    EIMS, PIMS) whose releases are included in the "Supporting" category even
    though their programme code does not appear in ``aliases``.
    """

    canonical: str = Field(description="Primary programme code used in the brain data.")
    aliases: list[str] = Field(
        default_factory=list,
        description="All known names and abbreviations for this value stream.",
    )
    related_programmes: list[str] = Field(
        default_factory=list,
        description="Supporting system programme codes whose releases belong to this VS.",
    )


class UiConfig(RRRModel):
    """Optional web dashboard authentication settings (ADR-0020, T-02).

    Set both ``auth_user`` and ``auth_password`` to protect ``rrr-ui`` with HTTP
    Basic Auth.  Leave both as ``null`` (the default) for local-only unauthenticated
    access — which is safe when the server is bound to ``127.0.0.1``.

    Use ``${VAR_NAME}`` interpolation (T-04) to inject the password from an
    environment variable so it never lands in the YAML file:

    .. code-block:: yaml

        ui:
          auth_user: "admin"
          auth_password: "${RRR_UI_PASSWORD}"
    """

    auth_user: str | None = Field(
        default=None,
        description="Username for HTTP Basic Auth. Null disables authentication entirely.",
    )
    auth_password: str | None = Field(
        default=None,
        description="Password for HTTP Basic Auth. Use ${VAR} to inject from env.",
    )

    @model_validator(mode="after")
    def _auth_pair_complete(self) -> UiConfig:
        """Require both user and password together — a partial config is always a mistake."""
        if (self.auth_user is None) != (self.auth_password is None):
            raise ValueError(
                "ui.auth_user and ui.auth_password must both be set or both be null"
            )
        return self


class RRRConfig(RRRModel):
    """Top-level validated configuration object."""

    schema_version: str
    weights: WeightsConfig
    thresholds: ThresholdsConfig
    trend: TrendConfig
    gates: GatesConfig
    timeouts: TimeoutsConfig
    persistence: PersistenceConfig
    tools: ToolsConfig
    provider: ProviderConfig
    sources: SourcesConfig
    assessors: AssessorsConfig
    memory: MemoryConfig
    value_stream: ValueStreamConfig | None = Field(
        default=None,
        description="Optional VS alias registry; enables category filtering in the Trends tab.",
    )
    tiers: TiersConfig | None = Field(
        default=None,
        description=(
            "Optional release risk tier configuration (ADR-0016 items 4-5). "
            "When present, the --tier CLI flag selects hotfix/standard/major thresholds. "
            "When absent, the global thresholds block is always used."
        ),
    )
    ui: UiConfig = Field(
        default_factory=UiConfig,
        description=(
            "Optional web dashboard authentication (ADR-0020). "
            "Set auth_user + auth_password to enable HTTP Basic Auth on rrr-ui."
        ),
    )
