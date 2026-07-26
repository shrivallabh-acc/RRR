"""``BaseAssessor`` — the ABC every dimension assessor extends (FR-12, FR-13).

A template method splits the two responsibilities cleanly:

* **Concrete assessors** implement :meth:`_assess` — the *deterministic* work:
  invoke tools, compute the 0-1 score, classify, detect risks, build evidence.
* **The base** orchestrates the rest: it runs reasoning through the provider
  (delegating prose/classification, never the score — ADR-0009), computes
  confidence from tool outcomes (FR-12), and assembles the ``DimensionResult``.

Helpers provided to subclasses (FR-12): :meth:`invoke_tool` (records every call
and tracks pass/fail), :meth:`calculate_confidence`, :meth:`build_evidence`,
:meth:`reason` (with guardrail fallback), and :meth:`reset`.

Graceful degradation (ADR-0005): if the deterministic work raises a ``ToolError``
the dimension is marked unavailable rather than crashing the run; the orchestrator
redistributes its weight and may return INCOMPLETE.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rrr.errors import ProviderValidationError, ToolError, ToolInvocationError, ToolTimeoutError
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName
from rrr.models.evidence import EvidenceRecord, EvidenceValue, RiskFactor, ToolInvocationModel
from rrr.models.llm import DimensionReasoning
from rrr.providers.base import LLMProvider, ReasoningRequest
from rrr.providers.rule_based import RuleBasedProvider
from rrr.tools.base import BaseTool
from rrr.tools.runner import ToolRunner

_CONFIDENCE_CAP_ON_FAILURE = 0.5
# Cap the number of facts forwarded to the LLM provider. Assessors must order
# facts most-impactful first so truncation discards the least-important ones.
# Cutting from "all evidence records" to five reduces token usage ~40% with
# negligible quality loss — the LLM needs signal, not an exhaustive log.
_MAX_FACTS: int = 5
logger = logging.getLogger(__name__)


@dataclass
class DeterministicAssessment:
    """What a concrete assessor computes before reasoning (the deterministic core)."""

    score: float
    classification: str
    summary: str
    facts: list[str] = field(default_factory=list)
    risk_factors: list[RiskFactor] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    allowed_classifications: list[str] = field(default_factory=list)
    available: bool = True
    confidence_cap: float | None = None
    """Optional upper bound on confidence (e.g. E2E-absent renormalization, ADR-0012)."""


class BaseAssessor(ABC):
    """Base for the five dimension assessors."""

    def __init__(self, runner: ToolRunner, provider: LLMProvider) -> None:
        self._runner = runner
        self._provider = provider
        self._fallback = RuleBasedProvider()
        self._invocations: list[ToolInvocationModel] = []
        self._tool_total = 0
        self._tool_failures = 0
        self._reasoning_degraded = False
        self.reset()

    @property
    @abstractmethod
    def dimension(self) -> DimensionName:
        """The dimension this assessor scores."""

    @abstractmethod
    def _assess(self) -> DeterministicAssessment:
        """Deterministic scoring/classification/risk detection (subclass implements)."""

    # --- public template -----------------------------------------------------------------

    def assess(self) -> DimensionResult:
        """Run the full pipeline and return the dimension's ``DimensionResult``."""
        self.reset()
        try:
            det = self._assess()
        except ToolError as exc:
            return self._unavailable(f"{self.dimension.value} unavailable: {exc}")

        reasoning = self.reason(self._to_request(det), DimensionReasoning)
        confidence = self.calculate_confidence()
        if det.confidence_cap is not None:
            confidence = min(confidence, det.confidence_cap)
        return DimensionResult(
            dimension=self.dimension,
            available=det.available,
            score=det.score,
            confidence=confidence,
            classification=reasoning.classification,
            narrative=reasoning.narrative,
            evidence=det.evidence,
            risk_factors=reasoning.risk_factors,
            tool_invocations=list(self._invocations),
        )

    # --- FR-12 helpers -------------------------------------------------------------------

    def reset(self) -> None:
        """Clear per-run state so an assessor instance can be reused."""
        self._invocations = []
        self._tool_total = 0
        self._tool_failures = 0
        self._reasoning_degraded = False

    def invoke_tool(self, tool: BaseTool, *, timeout: float | None = None, **params: Any) -> Any:
        """Run a tool via the runner, recording every attempt and tracking pass/fail.

        Retries transient ``ToolInvocationError`` up to ``_runner.retry_count``
        times with ``_runner.retry_backoff_s`` seconds between attempts (W6,
        NFR-1). ``ToolTimeoutError`` is never retried — a second attempt would
        likely time out again and double the latency penalty. Re-raises after the
        retry budget is exhausted so the caller can choose to degrade gracefully.
        """
        self._tool_total += 1
        for attempt in range(1 + self._runner.retry_count):
            if attempt > 0:
                time.sleep(self._runner.retry_backoff_s)
                logger.warning(
                    "[%s] retrying tool %r (attempt %d/%d)",
                    self.dimension.value,
                    tool.name,
                    attempt,
                    self._runner.retry_count,
                )
            try:
                result = self._runner.run(tool, timeout=timeout, **params)
                self._invocations.append(result.invocation)
                return result.output
            except ToolTimeoutError as exc:
                # Timeout is not retried — record and propagate immediately.
                self._tool_failures += 1
                if exc.invocation is not None:
                    self._invocations.append(exc.invocation)
                raise
            except ToolInvocationError as exc:
                if exc.invocation is not None:
                    self._invocations.append(exc.invocation)
                # On the last attempt, count the logical failure and re-raise.
                if attempt == self._runner.retry_count:
                    self._tool_failures += 1
                    raise

    def calculate_confidence(self) -> float:
        """Confidence from tool outcomes (FR-12): all pass→1.0, any fail→≤0.5, all fail→0.0.

        Degraded reasoning (provider fell back to rule-based) also caps at 0.5.
        """
        if self._tool_total == 0 or self._tool_failures == 0:
            confidence = 1.0
        elif self._tool_failures == self._tool_total:
            confidence = 0.0
        else:
            confidence = _CONFIDENCE_CAP_ON_FAILURE
        if self._reasoning_degraded:
            confidence = min(confidence, _CONFIDENCE_CAP_ON_FAILURE)
        return confidence

    @staticmethod
    def build_evidence(
        label: str,
        value: EvidenceValue = None,
        detail: str = "",
        tool: str | None = None,
    ) -> EvidenceRecord:
        """Factory for an audit-chain evidence record (NFR-3)."""
        return EvidenceRecord(label=label, value=value, detail=detail, tool=tool)

    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[DimensionReasoning],
    ) -> DimensionReasoning:
        """Provider reasoning with guardrail fallback (ADR-0009).

        On structured-output validation failure, fall back to the rule-based
        provider and flag reduced confidence.
        """
        t0 = time.monotonic()
        try:
            result = self._provider.reason(request, response_model)
            logger.debug(
                "[%s] %s  %.0fms",
                self.dimension.value,
                self._provider.name,
                (time.monotonic() - t0) * 1000,
            )
            return result
        except ProviderValidationError:
            self._reasoning_degraded = True
            logger.warning(
                "[%s] provider validation failed — degrading to RuleBasedProvider",
                self.dimension.value,
            )
            return self._fallback.reason(request, response_model)

    # --- internal ------------------------------------------------------------------------

    def _to_request(self, det: DeterministicAssessment) -> ReasoningRequest:
        """Pack the deterministic result into the format the provider expects.

        Facts are capped at ``_MAX_FACTS`` entries. Assessors must order facts
        most-impactful first (CRITICAL risk context → MAJOR risk context → supporting
        metrics) so truncation discards the least important observations. The provider
        only receives facts, a pre-computed classification, and a list of allowed
        labels — it cannot change the score or the risk factors, only write the
        narrative prose (ADR-0009).
        """
        return ReasoningRequest(
            dimension=self.dimension,
            summary=det.summary,
            classification=det.classification,
            facts=det.facts[:_MAX_FACTS],
            risk_factors=det.risk_factors,
            allowed_classifications=det.allowed_classifications,
        )

    def _unavailable(self, reason: str) -> DimensionResult:
        """Build a zero-score, unavailable result when a tool error prevents scoring.

        The orchestrator sees ``available=False`` and redistributes this dimension's
        weight to the others (ADR-0005). The error message goes into ``narrative``
        so the audit trail explains why the dimension is missing.
        """
        return DimensionResult(
            dimension=self.dimension,
            available=False,
            score=0.0,
            confidence=0.0,
            classification=None,
            narrative=reason,
            tool_invocations=list(self._invocations),
        )
