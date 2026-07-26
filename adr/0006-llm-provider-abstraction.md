# ADR 0006: LLMProvider Abstraction — Local-First, Deterministic Default

- **Status:** Accepted (implemented 2026-06-25)
- **Date:** 2026-06-08
- **Supersedes:** the earlier "Claude for in-agent reasoning" framing (Claude is now one
  provider behind this interface, used only when scaling externally in Phase 2).

## Context
RRR must be **demoable locally with nothing external** (a hard constraint): no outbound
network calls at runtime in Phase 1. It must still be **AI-first** — reasoning belongs to
an LLM, not hard-coded prose — and it must **scale outside** in Phase 2 without a rewrite.
These pull in different directions, so the reasoning engine must be swappable.

## Decision
Introduce an `LLMProvider` interface — `reason(prompt, schema) -> validated Pydantic
model` — with three implementations selected by `default_config.yaml`:

| Provider | Locality | Role |
|----------|----------|------|
| **`RuleBasedProvider`** | 100% local, no model | **Default.** Deterministic, template/heuristic narratives + risk extraction. Zero hardware cost, instant demo, used in CI and as the guardrail fallback. |
| **`LocalLLMProvider`** | 100% local (Ollama / llama.cpp on 127.0.0.1) | The **AI-first demo path** — a local instruct model (e.g. `llama3.1:8b` / `qwen2.5:7b`) generates classification, risk factors, rationale. No data leaves the machine. |
| **`ClaudeProvider`** | External (Anthropic API) | **Phase 2 opt-in** (✅ built 2026-06-25). Same interface; `claude-sonnet-4-6` default (configurable), `pip install rrr[cloud]`, `ANTHROPIC_API_KEY` env var. (see [ai-usage.md](../docs/ai-usage.md) Stage 3j). |

All three return **schema-validated structured output**; the assessor/orchestrator code
is identical regardless of provider. The numeric **score stays deterministic** in every
case — the provider only supplies judgment and prose (ADR-0009).

## Consequences
- Phase 1 demos with **no external calls and no required model** (`RuleBasedProvider`),
  yet is genuinely AI-first when a `LocalLLMProvider` is enabled — also fully on-machine.
- Phase 2 "scale outside" is a config change to `ClaudeProvider`, not a rewrite.
- Provider selection, model id, and endpoint live in config; defaults are local.
- Slightly more abstraction up front; pays for itself across the three deployment modes.
- See [adr/0010-local-first-no-external-runtime.md](0010-local-first-no-external-runtime.md)
  for the system-wide no-external guarantee this fits into.

## Implementation note — 2026-06-18
`LocalLLMProvider` built (`src/rrr/providers/local_llm.py`). Uses stdlib `urllib` (no SDK dep);
calls Ollama `/api/chat` with `format: json`; host allow-list checked at `__init__` per ADR-0010;
full `parse_with_repair` guardrail chain applies; network/HTTP errors re-raise as
`ProviderValidationError` so `BaseAssessor.reason()` degrades to `RuleBasedProvider` identically
to validation failures. `pipeline.py` factory now supports `provider.type: local_llm` (selects
endpoint + model from `[provider.local_llm]` config block). 14 unit tests cover all paths: normal,
repair, fallback, network error, allow-list enforcement.

## Implementation note — 2026-06-25
`ClaudeProvider` built (`src/rrr/providers/claude.py`). Uses the `anthropic` SDK (lazy import;
`pip install rrr[cloud]`) with Anthropic Messages API. API key resolved from `ANTHROPIC_API_KEY`
environment variable only — never config YAML. Full `parse_with_repair` guardrail chain applies
identically to `LocalLLMProvider`: 1 repair retry then `ProviderValidationError` for
`BaseAssessor.reason()` fallback. `pipeline.py` factory now supports `provider.type: claude` (reads
`[provider.claude]` block for model, max_tokens, temperature). Phase 2 unlocked.
13 unit tests cover: normal path, repair path, exhausted retries, API exception fallback, empty
content blocks, blank text, missing SDK, missing API key, missing config block, pipeline wiring.
