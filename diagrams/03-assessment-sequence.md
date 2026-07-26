# 3. Assessment Sequence (runtime interactions)

One full assessment over time: load → fan-out → assess (tools + Claude) → fan-in →
RAG → verdict synthesis → persist → emit.

> **Implementation status (M1–M6 complete + M7 Phase 2 Collect screen ✅ + hardening bundle ✅ — 727 tests as of 2026-07-10):** LangGraph `StateGraph` wrapper built (`orchestration/graph.py`,
> dispatch→collect, ADR-0002 impl-noted 2026-06-20); ThreadPoolExecutor runs inside the dispatch node by design
> (Python 3.14 thread compatibility — not a deviation). Chroma RAG built (optional, ADR-0007 impl-noted 2026-06-19).
> `ClaudeProvider` ✅ built 2026-06-25 (ADR-0006, Phase 2 opt-in). `rrr-ui` ✅ 2026-06-26 (ADR-0020).
> **M6 complete ✅ 2026-07-09:** 11 gate-only assessors (Security, Performance, Accessibility, Auditability, DisasterRecovery, DataReconciliation, FailureMode, DependencyRisk, ProductionReadiness, ArchitectureFitness, ArchitectureDrift); OperabilityAssessor + ObservabilityAssessor + RollbackAssessor split; Release Risk Tiers + sub-scores. All ADR-0016 items 1–16 built.
> **M7 Phase 1 ✅ 2026-07-09:** `rrr-collect` CLI (ADR-0023). **M7 Phase 2 Collect screen ✅ 2026-07-10:** `_collect_panel()` in `rrr-ui`. **Hardening bundle ✅ 2026-07-10:** WAL mode, env-var interpolation, HTTP Basic Auth, migration guard. Remaining: M7 Phase 2 tool adapters (snyk, sonarqube, k6, axe, grafana, datadog).

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant CLI as Click CLI
    participant Cfg as ConfigLoader
    participant Orc as Orchestrator (LangGraph)
    participant Asr as Assessor (×19, parallel)
    participant Tool as ToolRunner
    participant LLM as LLMProvider (local)
    participant Chr as Chroma (RAG)
    participant DB as SQLite
    participant Out as AssessmentOutputModel

    User->>CLI: rrr assess --input ...
    CLI->>Cfg: load + validate (Pydantic)
    Cfg-->>CLI: Config (weights sum=1.0)
    CLI->>Orc: run(config, inputs)

    par fan-out: 19 assessors in parallel (7 scored + 12 gate-only)
        Orc->>Asr: evaluate()
        Asr->>Tool: invoke_tool(...)
        Tool-->>Asr: data + ToolInvocationModel
        Note over Asr: deterministic score (MAPE / pass-rate / weighted)
        Asr->>LLM: reason(evidence, schema) → classify + risks + narrative
        LLM-->>Asr: structured output (Pydantic-validated)
        Asr-->>Orc: DimensionResult (score · confidence · evidence)
    end

    Note over Orc: fan-in — 7 scored dims → weighted sum; 12 gate-only dims → risk factors only<br/>GateEngine: CRITICAL risk → NO_GO cap; MAJOR → CONDITIONAL cap (ADR-0013)
    Orc->>Chr: query similar prior releases (RAG)
    Chr-->>Orc: benchmark / trend context
    Orc->>LLM: synthesize verdict rationale + remediation
    LLM-->>Orc: structured output (validated)
    Note over Orc: verdict LABEL derived from numeric score<br/>(GO / NO_GO / CONDITIONAL / INCOMPLETE)

    Orc->>DB: persist assessment (retry 3× / 5s)
    Orc->>Chr: embed + store summary (future RAG)
    Orc->>Out: build AssessmentOutputModel (schema 1.0.0)
    Out-->>CLI: verdict + score + audit trail
    CLI-->>User: "VERDICT: GO  SCORE: 84" + exit code
```
