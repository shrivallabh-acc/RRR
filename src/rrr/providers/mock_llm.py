"""``MockLLMProvider`` — fixture-backed demo provider for offline AI-first demos (Phase 1).

Loads pre-authored JSON responses from ``fixture_dir/`` and returns them as
schema-validated Pydantic models through the full ``parse_with_repair`` guardrail
chain. Demonstrates the AI-first pipeline end-to-end without requiring Ollama or
any model to be running.

Fixture file naming:
- Per-dimension: ``{dimension.value}.json``  (e.g. ``scope.json``, ``test_readiness.json``)
- Verdict synthesis: ``verdict_synthesis.json``

If a fixture file is missing, the provider silently falls back to
``RuleBasedProvider`` for that call so the demo never crashes on an incomplete
fixture set. This matches the production graceful-degradation posture (ADR-0005).

Select via ``provider.type: mock_llm`` with ``provider.mock_llm.fixture_dir: <path>``
in config (Phase 1 only — no external calls, fully local-first, ADR-0010).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from rrr.providers.base import LLMProvider, ReasoningModel, ReasoningRequest
from rrr.providers.guardrails import parse_with_repair
from rrr.providers.rule_based import RuleBasedProvider

logger = logging.getLogger(__name__)

# Sentinel JSON returned when a fixture file is absent — triggers guardrail repair
# path, which then falls back to RuleBasedProvider via ProviderValidationError.
_MISSING_FIXTURE_JSON = "{}"


class MockLLMProvider(LLMProvider):
    """Fixture-backed provider that demonstrates AI reasoning offline.

    Reads JSON from ``fixture_dir``; returns validated structured outputs through
    the same guardrail chain as LocalLLMProvider so the pipeline is exercise
    identically to production. Designed for demos and CI environments that do not
    have a running local model.
    """

    def __init__(
        self,
        fixture_dir: str | Path,
        *,
        repair_retries: int = 1,
    ) -> None:
        """Create a provider backed by pre-authored JSON fixtures.

        :param fixture_dir: Directory containing ``{dimension}.json`` and
            ``verdict_synthesis.json`` fixture files.
        :param repair_retries: Extra repair attempts passed to parse_with_repair
            (default 1, matching ADR-0009 policy).
        """
        self._fixture_dir = Path(fixture_dir)
        self._repair_retries = repair_retries
        self._fallback = RuleBasedProvider()

    @property
    def name(self) -> str:
        return "MockLLMProvider"

    def reason(
        self,
        request: ReasoningRequest,
        response_model: type[ReasoningModel],
    ) -> ReasoningModel:
        """Return a schema-validated model loaded from the matching fixture file.

        Determines the fixture path from the request dimension (per-assessor) or
        falls back to ``verdict_synthesis.json`` (orchestrator call). Pipes the
        fixture JSON through ``parse_with_repair`` so the guardrail chain is fully
        exercised. If the fixture is absent or invalid after repairs, delegates to
        ``RuleBasedProvider`` with a warning — the assessment continues rather than
        crashing.
        """
        fixture_path = self._resolve_fixture(request)
        json_str = self._load_fixture(fixture_path)

        def generate(repair_hint: str | None) -> str:
            """Return fixture JSON; repair_hint is ignored (fixtures are pre-valid)."""
            return json_str

        try:
            return parse_with_repair(generate, response_model, max_repairs=self._repair_retries)
        except Exception as exc:
            # Missing or invalid fixture — degrade to rule-based rather than crash.
            logger.warning(
                "MockLLMProvider fixture %s failed validation (%s); using RuleBasedProvider",
                fixture_path.name,
                exc,
            )
            return self._fallback.reason(request, response_model)

    # ------------------------------------------------------------------

    def _resolve_fixture(self, request: ReasoningRequest) -> Path:
        """Pick the fixture file for this request.

        Uses the dimension name for assessor calls and ``verdict_synthesis`` for
        the orchestrator's cross-dimension synthesis call. Both are stored flat in
        ``fixture_dir``.
        """
        name = request.dimension.value if request.dimension is not None else "verdict_synthesis"
        return self._fixture_dir / f"{name}.json"

    def _load_fixture(self, path: Path) -> str:
        """Read the fixture file and return its content as a string.

        Returns the missing-fixture sentinel (``"{}"``) if the file does not exist
        so that ``parse_with_repair`` exercises the validation → repair path, which
        then raises ``ProviderValidationError`` and triggers the ``RuleBasedProvider``
        fallback in ``reason()``.
        """
        if not path.exists():
            logger.warning("MockLLMProvider: fixture not found at %s — will use fallback", path)
            return _MISSING_FIXTURE_JSON
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            # File exists but cannot be read (permissions, encoding error, etc.).
            logger.warning("MockLLMProvider: cannot read fixture %s: %s", path, exc)
            return _MISSING_FIXTURE_JSON

    def load_fixture_raw(self, name: str) -> dict[str, Any]:
        """Load a fixture by name and return the raw dict (test helper).

        Convenience for tests that want to inspect fixture content without going
        through the full provider call. Not used in the production pipeline.
        """
        path = self._fixture_dir / f"{name}.json"
        return cast(dict[str, Any], json.loads(self._load_fixture(path)))
