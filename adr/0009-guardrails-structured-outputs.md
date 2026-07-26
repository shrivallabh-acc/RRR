# ADR 0009: Guardrails via Pydantic Structured Outputs + Repair Loop

- **Status:** Accepted (implemented 2026-06-25)
- **Date:** 2026-06-08

## Context
An agentic system that influences a high-stakes decision must handle **hallucinations and
guardrails** defensively. RRR's LLM calls must not be able to corrupt the verdict or emit
unvalidated data.

## Decision
Every `LLMProvider.reason()` call returns **structured output validated against a Pydantic
v2 model** (Claude: `messages.parse()`/`output_config.format`; local LLM: JSON/format mode
then Pydantic-validate; rule-based: constructs the model directly). Guardrails:
1. **Schema constraint** — the provider can only return the shape we defined; invalid
   fields are rejected by Pydantic before they enter the pipeline.
2. **Repair loop** — on validation failure (or a refusal), retry once with the validation
   error fed back; if it still fails, the dimension falls back to the `RuleBasedProvider`
   (deterministic-only narrative) and is marked reduced-confidence (ties into
   `calculate_confidence()` and graceful degradation, ADR-0005).
3. **Score authority** — the LLM never sets the numeric score or the verdict label; it
   only classifies ambiguous items and writes prose. The verdict derives from
   deterministic math, bounding the blast radius of any bad generation.
4. **Injection safety** — ingested `brain/*.json` and source data are passed as *data*,
   never as instructions; the system prompt is fixed and prompt-cached.

## Consequences
- Hallucinations cannot produce malformed output or silently change the verdict.
- Clean, demoable answer to the "how do you handle hallucinations / guardrails" question.
- One extra retry in the worst case; bounded by the repair-then-degrade policy.

## Implementation note — 2026-06-25
Guardrail chain (`parse_with_repair` in `providers/guardrails.py`) extended to `ClaudeProvider`.
All three paths verified by 13 unit tests in `tests/unit/test_claude_provider.py`: normal
(valid first response), repair (invalid first → valid second), exhausted (both invalid →
`ProviderValidationError`). API-level errors (auth failure, rate-limit, network) are caught in
`ClaudeProvider._call_claude()` and re-raised as `ProviderValidationError` — the fallback path
handles both API errors and schema failures identically.
