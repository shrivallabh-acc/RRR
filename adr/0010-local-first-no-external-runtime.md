# ADR 0010: Local-First — No External Runtime Dependencies (Phase 1)

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
Phase 1 must be a **locally demoable utility with nothing external**: no outbound network
calls, no cloud accounts, no hosted services at runtime. Everything required runs on the
user's machine. Phase 2 may scale outside, but only as an explicit, opt-in change.

## Decision
Every runtime component is on-machine by default. External capability exists only behind
an interface and is **off unless explicitly configured** for Phase 2.

| Concern | Phase 1 (local, default) | Phase 2 (opt-in external) |
|---------|--------------------------|---------------------------|
| Reasoning | `RuleBasedProvider` (no model) or `LocalLLMProvider` (Ollama/llama.cpp on 127.0.0.1) | `ClaudeProvider` (Anthropic API) — ADR-0006 |
| Canonical store | SQLite file on disk | (unchanged or managed DB) |
| Vector memory / RAG | Chroma embedded (local files) | (unchanged or hosted vector DB) |
| Embeddings | Local sentence-transformer model | (unchanged or hosted embeddings) |
| Environment / Dependency data | Local JSON/CSV files **+ localhost (127.0.0.1) mock APIs** | Live external APIs |
| Config / output | YAML, JSON, Markdown on disk | (unchanged) |

**No-external rules:**
1. Default config selects only local providers/sources; a fresh checkout runs offline.
2. Any external endpoint must be explicitly set in config and is rejected by default
   (allowlist: `127.0.0.1` / `localhost` in Phase 1).
3. CI and the evaluation harness run fully offline using `RuleBasedProvider`.
4. Model weights (if a local LLM is used) are pulled **once** during setup — not a
   runtime network dependency.

## Consequences
- A clean clone demos with no setup beyond `pip install` (and an optional one-time
  `ollama pull` if the AI-first demo path is wanted).
- Air-gap friendly; nothing leaves the machine; no secrets required in Phase 1.
- Phase 2 scale-out is gated behind explicit config, preserving the local guarantee by
  default.
- Tied to [adr/0003-sqlite-for-persistence.md](0003-sqlite-for-persistence.md),
  [adr/0006-llm-provider-abstraction.md](0006-llm-provider-abstraction.md),
  [adr/0007-chroma-vector-memory.md](0007-chroma-vector-memory.md).
