# ADR 0007: Chroma Vector Store for Memory + RAG Benchmarking

- **Status:** Accepted (implemented 2026-06-19)
- **Date:** 2026-06-08

## Context
RRR needs a **context/memory engine** with memory that **persists across stages**, plus a
defensible **benchmark** and
**trend** story: "how does this release compare to similar past ones?" SQLite stores the
canonical record but isn't a semantic-retrieval engine.

## Decision
Use **Chroma** (embedded, file-based, zero-infra) as the vector memory. After each
assessment, embed a structured summary (dimension scores, verdict, key risks) and store
it. At verdict time the orchestrator **RAG-retrieves the most similar prior releases** to
ground the benchmark and trend narrative that Claude writes.

SQLite remains the **system of record** (ADR-0003); Chroma is the **semantic index over
it**. They are kept consistent on each persist.

## Consequences
- Satisfies the context/memory-engine constraint with a real vector store, no servers.
- Enables RAG: the verdict rationale can cite comparable historical releases.
- Two stores to keep in sync; persistence writes to both under the existing retry policy.
- Embedding model choice is configurable; defaults to a local sentence-transformer to
  avoid extra API cost.

## Implementation note (2026-06-19)
Built and tested. `chromadb` 1.5.9 confirmed importable on Python 3.14.4 / Windows.
Embedding strategy: 6D score vector [scope, estimation, environment, test_readiness,
dependency, overall_score/100] — no external embedding model needed (local-first, ADR-0010).
`AssessmentStore` gains `chroma_path` kwarg; `":memory:"` uses `EphemeralClient` with a
UUID-suffixed collection name for test isolation. `chroma_path: null` in config disables RAG
silently — all pipeline behaviour unchanged. `similar_to(output, k=3)` is best-effort
(returns `[]` on any Chroma error). Config default is `null`; users opt in by setting
`memory.chroma_path` to a directory path. The sentence-transformer embedding noted in the
decision was superseded by the score-vector approach to eliminate the sentence-transformers
dependency and keep the store fully local with zero ML model overhead.
