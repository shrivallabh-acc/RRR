"""``Orchestrator`` — fan out the assessors, fuse scores, derive the verdict (FR-6/7/8/22).

Assessors run in parallel (``ThreadPoolExecutor``; each is an independent instance
with no shared mutable state). Results are fused into a weighted score with
redistribution (:mod:`scoring`), the verdict is derived with veto/cap gates
(:mod:`verdict`), and the provider synthesizes the rationale + remediation — but
the verdict *label* comes from the deterministic score/gates, never the provider
(ADR-0009 #3). The whole assessment is returned as an ``AssessmentOutputModel``.

``run()`` is the convenience entry point (fan-out + collect). ``_fan_out()`` and
``collect()`` are public so LangGraph (ADR-0002, optional tracing layer) can split
the two phases without duplicating scoring/synthesis logic inside the graph node.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait

from rrr.assessors.base import BaseAssessor
from rrr.config.schema import RRRConfig
from rrr.errors import ProviderValidationError
from rrr.models.assessment import AssessmentOutputModel, AuditTrail
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, ReleaseRiskTier
from rrr.models.evidence import RiskFactor, ToolInvocationModel
from rrr.models.llm import VerdictSynthesis
from rrr.orchestration.scoring import split_scores, weighted_score
from rrr.orchestration.verdict import derive_verdict
from rrr.providers.base import LLMProvider, ReasoningRequest
from rrr.providers.rule_based import RuleBasedProvider

logger = logging.getLogger(__name__)
_DIMENSION_ORDER = {dim: i for i, dim in enumerate(DimensionName)}


class Orchestrator:
    """Fuses the five assessors into one auditable verdict."""

    def __init__(
        self,
        config: RRRConfig,
        provider: LLMProvider,
        *,
        max_workers: int | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._fallback = RuleBasedProvider()
        self._max_workers = max_workers

    def run(
        self,
        assessors: list[BaseAssessor],
        *,
        release: str,
        value_stream: str = "",
        tier: ReleaseRiskTier | None = None,
    ) -> AssessmentOutputModel:
        """Assess all dimensions and return the complete assessment.

        Convenience entry point: fan-out in parallel then hand off to
        :meth:`collect`. Callers that need to split the two phases (e.g. the
        LangGraph wrapper in :mod:`graph`) can call ``_fan_out`` + ``collect``
        directly without going through this method.

        ``tier`` selects a threshold override set (ADR-0016 items 4-5). When
        None, the global thresholds in config are used.
        """
        run_id = str(uuid.uuid4())[:8]
        t_start = time.monotonic()
        logger.info(
            "run_id=%s  release=%r  provider=%s  assessors=%d  tier=%s",
            run_id,
            release,
            self._provider.name,
            len(assessors),
            tier.value if tier is not None else "none",
        )

        t_fanout = time.monotonic()
        results = self._fan_out(assessors)
        logger.info(
            "run_id=%s  fan-out complete  elapsed=%.2fs", run_id, time.monotonic() - t_fanout
        )

        t_synth = time.monotonic()
        output = self.collect(results, release=release, value_stream=value_stream, tier=tier)
        logger.debug("run_id=%s  collect elapsed=%.2fs", run_id, time.monotonic() - t_synth)

        logger.info(
            "run_id=%s  verdict=%s  score=%d  total=%.2fs",
            run_id,
            output.verdict.value,
            output.score,
            time.monotonic() - t_start,
        )
        return output

    def collect(
        self,
        results: list[DimensionResult],
        *,
        release: str,
        value_stream: str = "",
        tier: ReleaseRiskTier | None = None,
    ) -> AssessmentOutputModel:
        """Score, apply gates, synthesize, and build the output from pre-computed fan-out results.

        Separated from :meth:`run` so callers that already have ``DimensionResult``
        objects (e.g. the LangGraph ``collect`` node, batch re-scoring tools) can
        run this phase without re-executing the assessors. All deterministic logic
        lives here; ``_fan_out`` only owns parallel execution.

        ``tier`` selects a threshold override from ``config.tiers`` (ADR-0016 items 4-5).
        When None, the global thresholds are used. The tier label is passed through
        to ``AssessmentOutputModel`` so the output records which tier was active.
        """
        weights = self._weights()
        score, effective = weighted_score(results, weights)
        available = [r for r in results if r.available]
        aggregate_confidence = (
            sum(r.confidence for r in available) / len(available) if available else None
        )

        # Resolve tier-specific thresholds when a tier is active (ADR-0016 items 4-5).
        tier_thresholds = None
        if tier is not None and self._config.tiers is not None:
            tier_thresholds = self._config.tiers.for_tier(tier)

        verdict, gates_triggered = derive_verdict(
            score,
            results,
            self._config.thresholds,
            self._config.gates,
            aggregate_confidence=aggregate_confidence,
            tier_thresholds=tier_thresholds,
        )
        score_100 = round(score * 100)

        # Compute ship-safety and delivery-performance sub-scores (ADR-0016 item 6).
        ship_raw, delivery_raw = split_scores(results, weights)
        ship_100 = round(ship_raw * 100) if ship_raw is not None else None
        delivery_100 = round(delivery_raw * 100) if delivery_raw is not None else None

        synthesis = self._synthesize(results, verdict.value, score_100)

        risk_factors: list[RiskFactor] = [rf for r in results for rf in r.risk_factors]
        invocations: list[ToolInvocationModel] = [
            inv for r in results for inv in r.tool_invocations
        ]
        audit = AuditTrail(
            provider=self._provider.name,
            effective_weights=effective,
            tool_invocations=invocations,
            gates_triggered=gates_triggered,
        )
        return AssessmentOutputModel(
            release=release,
            value_stream=value_stream,
            verdict=verdict,
            score=score_100,
            tier=tier,
            ship_safety_score=ship_100,
            delivery_performance_score=delivery_100,
            aggregate_confidence=aggregate_confidence,
            dimensions=results,
            rationale=synthesis.rationale,
            remediation=synthesis.remediation,
            risk_factors=risk_factors,
            audit_trail=audit,
        )

    def _fan_out(self, assessors: list[BaseAssessor]) -> list[DimensionResult]:
        """Run all assessors in parallel, applying a per-assessor hard timeout (NFR-1).

        All assessors are submitted to a thread pool at once so they run concurrently.
        ``wait(timeout=assessor_default)`` then gives every parallel assessor its own
        full time budget — futures that finish quickly return immediately; only a
        genuinely stuck assessor consumes the whole window.

        Assessors that exceed the deadline land in ``not_done`` and are emitted as
        unavailable DimensionResults so the orchestrator can redistribute weight
        (ADR-0005) rather than hanging the CLI. Python threads cannot be forcibly
        killed, so stuck threads are abandoned via ``shutdown(wait=False)`` — they
        finish naturally or are reaped when the process exits.

        Results are sorted by a fixed dimension order after collection so the output
        is deterministic regardless of which assessor finished first (ADR-0002).
        """
        if not assessors:
            return []
        timeout_secs = float(self._config.timeouts.assessor_default)
        workers = self._max_workers or len(assessors)
        results: list[DimensionResult] = []

        # Don't use `with` so we control whether to wait=False on shutdown.
        executor = ThreadPoolExecutor(max_workers=workers)
        futures: dict[Future[DimensionResult], BaseAssessor] = {
            executor.submit(assessor.assess): assessor for assessor in assessors
        }
        done, not_done = wait(list(futures), timeout=timeout_secs)

        for future in done:
            try:
                results.append(future.result())
            except Exception as exc:
                # assess() handles ToolError and returns unavailable; this catches
                # any truly unexpected exception so the fan-out never propagates.
                assessor = futures[future]
                logger.error(
                    "[%s] unexpected error during assessment — marking unavailable: %s",
                    assessor.dimension.value,
                    exc,
                )
                results.append(assessor._unavailable(str(exc)))

        for future in not_done:
            assessor = futures[future]
            logger.warning(
                "[%s] assessor timed out after %.0fs — marking unavailable (NFR-1)",
                assessor.dimension.value,
                timeout_secs,
            )
            results.append(
                assessor._unavailable(
                    f"{assessor.dimension.value} timed out after {timeout_secs:.0f}s"
                )
            )

        # Abandon stuck threads — they run until naturally done or process exit.
        executor.shutdown(wait=False)

        # Stable order regardless of completion order — keeps output deterministic.
        results.sort(key=lambda r: _DIMENSION_ORDER[r.dimension])
        return results

    def _weights(self) -> dict[DimensionName, float]:
        """Convert the config weight fields into the dict that weighted_score expects.

        The config stores each weight as a named field (e.g. ``weights.scope``).
        weighted_score works with a DimensionName-keyed dict, so this method just
        re-shapes the same values. Weights must sum to 1.0 — enforced at load time
        by WeightsConfig's model validator, so we don't re-check here.
        OPERABILITY and OBSERVABILITY replace the old OPERATIONAL (ADR-0016 item 7).
        """
        w = self._config.weights
        return {
            DimensionName.SCOPE: w.scope,
            DimensionName.ESTIMATION: w.estimation,
            DimensionName.ENVIRONMENT: w.environment,
            DimensionName.TEST_READINESS: w.test_readiness,
            DimensionName.DEPENDENCY: w.dependency,
            DimensionName.OPERABILITY: w.operability,
            DimensionName.OBSERVABILITY: w.observability,
        }

    def _synthesize(
        self,
        results: list[DimensionResult],
        verdict_label: str,
        score_100: int,
    ) -> VerdictSynthesis:
        """Ask the provider to write the overall verdict rationale and remediation plan.

        Assembles one fact string per dimension (score + classification + availability)
        and passes them to the provider as data, not instructions — so the LLM cannot
        influence the numeric outcome, only the prose it wraps around it (ADR-0006).
        """
        facts = [
            f"{r.dimension.value}: score {r.score:.2f}"
            + (f" ({r.classification})" if r.classification else "")
            + ("" if r.available else " [unavailable]")
            for r in results
        ]
        summary = (
            f"Verdict {verdict_label} at score {score_100}/100 across {len(results)} dimensions."
        )
        request = ReasoningRequest(
            summary=summary,
            facts=facts,
            risk_factors=[rf for r in results for rf in r.risk_factors],
        )
        try:
            return self._provider.reason(request, VerdictSynthesis)
        except ProviderValidationError:
            return self._fallback.reason(request, VerdictSynthesis)
