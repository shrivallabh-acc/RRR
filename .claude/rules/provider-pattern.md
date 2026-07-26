---
description: Enforce LLMProvider interface and guardrail chain for all provider implementations
globs: ["src/rrr/providers/*.py"]
---

When creating or modifying any file in `src/rrr/providers/`:

## The guardrail chain (ADR-0009) — never bypass
Every LLM call MUST pass through this chain in order:

```
LLMProvider.reason(request) → raw output
  → parse_with_repair(raw, schema)   # 1 repair retry
    → on second failure: RuleBasedProvider.reason(request)  # fallback
      → DimensionResult.confidence_cap applied (reduced confidence)
```

- Never call the LLM directly (raw HTTP / SDK) from outside a `LLMProvider` subclass.
- Never return unvalidated LLM output — every response MUST be Pydantic-validated before leaving the provider.
- Never suppress the fallback — if the repair fails twice, the `RuleBasedProvider` MUST run.

## Injection safety (ADR-0009)
- `ReasoningRequest.facts` carries DATA — strings extracted from tool results.
- `ReasoningRequest.summary` / instruction fields carry INSTRUCTIONS.
- Never interpolate raw user input or tool output into the instruction fields.
- `allowed_classifications` MUST be set to bound the label space — open-ended classification is not permitted.

## Local-first (ADR-0010, Phase 1)
- Phase 1 providers: `RuleBasedProvider` (no model) and `LocalLLMProvider` (`127.0.0.1` only).
- `ClaudeProvider` (Anthropic API) is Phase 2 only — do not wire it into Phase 1 pipeline paths.
- Any new provider that makes an outbound network call MUST check the host allow-list from `ConfigLoader`.

## Single-LLM-call ceiling (ADR-0017)
- Each assessor makes exactly ONE provider call (the dimension narrative).
- The orchestrator makes exactly ONE provider call (verdict rationale + remediation).
- Do not introduce prompt chaining, multi-turn loops, or agent-style iteration without a new ADR.

## Tests
- New providers MUST have unit tests in `tests/unit/test_<provider_name>.py`.
- Tests MUST cover: normal path, repair path (malformed first response), fallback path (repair exhausted).
