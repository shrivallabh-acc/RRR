# 6. Memory & RAG

Two stores, kept consistent on each persist: **SQLite** is the system of record;
**Chroma** is the semantic index over it that powers RAG benchmarking (ADR-0003, ADR-0007).

> **Implementation status (M4 complete):** SQLite `AssessmentStore` ✅ built (ADR-0003).
> Chroma RAG ✅ built (optional 6D score-vector, `chroma_path: null` disables; `":memory:"` for tests;
> ADR-0007 impl-noted 2026-06-19). Note: the diagram shows `sentence-transformer` embeddings; as-built
> uses a 6-dimensional numeric vector `[scope, estimation, environment, test_readiness, dependency, score/100]`
> for dependency-free local operation. Full semantic embeddings are a Phase 2 / M5 enhancement.

```mermaid
flowchart LR
    subgraph WRITE["Write path (end of each assessment)"]
        direction TB
        ASMT["Assessment result<br/>(verdict · scores · risks)"]
        ASMT --> SQL[("SQLite<br/>canonical record<br/>retention_days: 90")]
        ASMT --> EMB["Embed summary<br/>(local sentence-transformer)"]
        EMB --> VEC[("Chroma<br/>vector store")]
    end

    subgraph READ["Read path (at verdict time)"]
        direction TB
        Q["Current release summary"] --> SIM["similarity search<br/>top-k prior releases"]
        VEC -. retrieve .-> SIM
        SIM --> CTX["Benchmark + trend context"]
        CTX --> LLMV["LLMProvider verdict rationale<br/>(RAG-grounded, local)"]
    end

    subgraph TREND["Trend comparison"]
        direction TB
        PREV["Previous assessment<br/>(from SQLite)"] --> DELTA{"per-dimension Δ"}
        DELTA -- "Δ > 0.05" --> IMP["improving"]
        DELTA -- "Δ < -0.05" --> DEG["degrading"]
        DELTA -- "else" --> STA["stable"]
    end

    classDef store fill:#fef7e0,stroke:#f9ab00;
    classDef ai fill:#e8f5e9,stroke:#34a853;
    class SQL,VEC store;
    class EMB,SIM,LLMV ai;
```
