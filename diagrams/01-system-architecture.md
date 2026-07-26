# 1. System Architecture

End-to-end view. Deterministic components in blue, AI components in green, storage in
amber. **Everything shown runs locally** (Phase 1, ADR-0010) — see
[diagram 9](09-deployment.md) for the local vs. Phase-2-external boundary.

> **Implementation status (M1–M6 complete + M7 Phase 2 Collect screen ✅ + hardening bundle ✅ — 727 tests as of 2026-07-10):** LangGraph `StateGraph` wrapper built
> (`orchestration/graph.py`, dispatch→collect, ADR-0002 impl-noted 2026-06-20); ThreadPoolExecutor runs inside
> the dispatch node. Chroma RAG built (optional 6D vector, ADR-0007 impl-noted 2026-06-19). `MockLLMProvider`
> + `LocalLLMProvider` + `BedrockProvider` (ADR-0019) + `ClaudeProvider` ✅ 2026-06-25 available.
> `rrr-ingest` HTML ingest layer ✅ 2026-06-22 (ADR-0018). NiceGUI `rrr-ui` ✅ 2026-06-26 (ADR-0020, `pip install rrr[ui]`).
> **M6 complete ✅ 2026-07-09:** Release Risk Tiers + ship-safety/delivery sub-scores; `OperabilityAssessor` + `ObservabilityAssessor` + `RollbackAssessor` (split from OperationalAssessor); 9 gate-only assessors (Accessibility, Auditability, DisasterRecovery, DataReconciliation, FailureMode, DependencyRisk, ProductionReadiness, ArchitectureFitness, ArchitectureDrift) — all ADR-0016 items 1–16 built.
> **M7 Phase 1 ✅ 2026-07-09:** `rrr-collect` CLI + `CollectorRunner` + `CollectorRegistry` + `InteractiveCollector` (ADR-0023).
> **M7 Phase 2 Collect screen ✅ 2026-07-10:** `_collect_panel()` in `rrr-ui` (FRESH/STALE/MISSING status view, InputContract-driven form, `_DictCollector` shared write path).
> **Hardening bundle ✅ 2026-07-10:** T-03 WAL mode, T-04 env-var interpolation, T-02 HTTP Basic Auth, T-07 SQLite migration guard.
> **Remaining:** M7 Phase 2 tool adapters (snyk, sonarqube, k6, axe, grafana, datadog); optional hosted persistence.

```mermaid
flowchart TB
    subgraph IN["Inputs"]
        BRAIN["brain/*.json<br/>(RKT Program Metrics — via rrr-ingest)"]
        SUPP["data/*.json<br/>(supplementary — via rrr-collect CLI)"]
    end

    subgraph CFG["Configuration"]
        YAML["default_config.yaml"]
        LOADER["ConfigLoader<br/>YAML → defaults → Pydantic v2"]
        YAML --> LOADER
    end

    subgraph ORCH["Orchestration — LangGraph"]
        DISPATCH["Dispatch node<br/>(fan-out)"]
        COLLECT["Collect node<br/>(fan-in + weighting)"]
        VERDICT["Verdict + LLM rationale<br/>+ remediation"]
        DISPATCH --> COLLECT --> VERDICT
    end

    subgraph AGENTS["19 Assessor Agents — BaseAssessor ABC"]
        SCORED["7 Scored Assessors (contribute to weighted score)<br/>Scope 0.25 · Estimation 0.10 · Environment 0.20<br/>Test Readiness 0.20 · Dependency 0.15<br/>Operability 0.07 · Observability 0.03"]
        GATED["12 Gate-Only Assessors (weight=0 · risk factors → verdict cap)<br/>Security · Performance · Rollback · Accessibility<br/>Auditability · Disaster Recovery · Data Reconciliation<br/>Failure Mode · Dependency Risk · Production Readiness<br/>Architecture Fitness · Architecture Drift"]
    end

    subgraph AI["AI + Tools"]
        LLM["LLMProvider (pluggable)<br/>RuleBased default · LocalLLM (Ollama)<br/>· Claude = Phase 2"]
        TOOLS["ToolRunner + BaseTool(s)<br/>timeout · invocation recording"]
    end

    subgraph MEM["Memory (local)"]
        SQLITE[("SQLite<br/>canonical records")]
        CHROMA[("Chroma (embedded)<br/>vector store / RAG")]
    end

    subgraph OUT["Output"]
        MODEL["AssessmentOutputModel<br/>JSON schema 1.0.0"]
        CLI["Click CLI<br/>verdict line · --verbose · exit codes"]
        MD["Jinja2 Markdown<br/>plans / checklists"]
    end

    IN --> LOADER
    LOADER --> DISPATCH
    DISPATCH --> AGENTS
    AGENTS --> TOOLS
    AGENTS --> LLM
    AGENTS --> COLLECT
    CHROMA -. RAG .-> VERDICT
    VERDICT --> LLM
    VERDICT --> SQLITE
    VERDICT --> CHROMA
    VERDICT --> MODEL
    MODEL --> CLI
    MODEL --> MD

    classDef det fill:#e3f2fd,stroke:#1a73e8,color:#202124;
    classDef ai fill:#e8f5e9,stroke:#34a853,color:#202124;
    classDef store fill:#fef7e0,stroke:#f9ab00,color:#202124;
    classDef gate fill:#fce8e6,stroke:#d93025,color:#202124;
    class LOADER,DISPATCH,COLLECT,TOOLS,MODEL,CLI,MD,SCORED det;
    class LLM,VERDICT ai;
    class SQLITE,CHROMA store;
    class GATED gate;
```
