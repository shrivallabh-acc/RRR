# 9. Deployment — Local-First Boundary (Phase 1) vs. External Scale (Phase 2)

The whole of Phase 1 runs inside one machine with no outbound calls (ADR-0010). Every
external capability sits behind an interface and is **off unless explicitly configured**
for Phase 2 — no rewrite to switch (ADR-0006).

> **Implementation status (M1–M6 complete + M7 Phase 1 complete — 708 tests as of 2026-07-09):** Phase 1 + Phase 2 fully complete. `ClaudeProvider` ✅ built 2026-06-25
> (Phase 2 opt-in). NiceGUI `rrr-ui` ✅ built 2026-06-26 (ADR-0020, `pip install rrr[ui]` — local web server).
> Live external APIs ✅ built 2026-06-28 (`ApiSource` HTTP transport). Hosted persistence interface ✅ (`AbstractAssessmentStore` + `RemoteAssessmentStore` stub) — remote backend implementation pending host/auth design.
> **M7 Phase 1 ✅ 2026-07-09:** `rrr-collect` CLI (ADR-0023). Remaining: M7 Phase 2 — `rrr-ui` Collect screen + tool adapters.

```mermaid
flowchart LR
    subgraph LOCAL["🖥️ Your machine — Phase 1 (default, no external calls)"]
        direction TB
        CLI["RRR CLI (Click)"]
        UISRV["NiceGUI rrr-ui<br/>(local web server · ✅ built 2026-06-26)<br/>pip install rrr[ui]"]
        ORCH["Orchestrator + 5 assessors"]
        RULE["RuleBasedProvider<br/>(default · no model)"]
        OLLAMA["LocalLLMProvider<br/>Ollama / llama.cpp @ 127.0.0.1<br/>(optional · AI-first demo)"]
        TOOLS["ToolRunner + tools"]
        SQL[("SQLite")]
        CHR[("Chroma + local embeddings")]
        FILES["brain/*.json · env/dep files"]
        MOCK["localhost mock APIs<br/>(127.0.0.1)"]

        CLI --> ORCH
        UISRV -. opt-in .-> SQL
        ORCH --> RULE
        ORCH -. opt-in .-> OLLAMA
        ORCH --> TOOLS
        ORCH --> SQL
        ORCH --> CHR
        TOOLS --> FILES
        TOOLS --> MOCK
    end

    subgraph EXT["☁️ Phase 2 — scale outside (opt-in, same interfaces)"]
        direction TB
        CLAUDE["ClaudeProvider<br/>Anthropic API · claude-sonnet-4-6 (default)<br/>✅ built 2026-06-25"]
        LIVEAPI["Live external<br/>Environment / Dependency APIs"]
        HOSTED["Optional hosted<br/>DB / vector store"]
    end

    ORCH -. "provider=claude (Phase 2 only)" .-> CLAUDE
    TOOLS -. "allow external host (Phase 2 only)" .-> LIVEAPI
    CHR -. "swap behind memory interface" .-> HOSTED

    GATE{{"Egress gate — non-local endpoints rejected unless allowlisted"}}
    ORCH --- GATE
    GATE -. blocks by default .-> EXT

    classDef local fill:#e8f5e9,stroke:#34a853;
    classDef ext fill:#fce8e6,stroke:#d93025;
    classDef gate fill:#fef7e0,stroke:#f9ab00;
    class CLI,UISRV,ORCH,RULE,OLLAMA,TOOLS,SQL,CHR,FILES,MOCK local;
    class CLAUDE,LIVEAPI,HOSTED ext;
    class GATE gate;
```

**Read it as:** green = on your machine (the entire Phase-1 product); red = external,
reachable only when you flip a config flag in Phase 2; amber = the egress gate that
rejects non-local endpoints by default. A fresh clone runs entirely in the green box.
