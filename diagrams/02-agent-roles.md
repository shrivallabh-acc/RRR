# 2. Agent Roles & Tool Interfaces

The orchestrator fans out to 19 assessor agents. Every assessor extends `BaseAssessor`
and reaches the outside world only through two interfaces: `ToolRunner` (data) and
`LLMProvider` (reasoning). **Scored assessors** contribute to the weighted score;
**gate-only assessors** (weight=0) produce CRITICAL/MAJOR risk factors that cap the verdict
via the GateEngine (ADR-0013/0014).

```mermaid
flowchart TB
    ORCH["Orchestrator<br/>(LangGraph fan-out · fan-in · verdict)"]

    subgraph BA["BaseAssessor (ABC) — template method pattern"]
        direction LR
        M1["_assess() → DeterministicAssessment<br/>(score + risk factors — pure math)"]
        M2["reason() via LLMProvider<br/>(narrative only — never sets score)"]
        M3["invoke_tool() via ToolRunner<br/>(timeout + invocation recording)"]
        M4["calculate_confidence() FR-12"]
    end

    subgraph SCORED["7 Scored Assessors — weighted, contribute to numeric score"]
        direction LR
        SC["Scope<br/>0.25"]
        ES["Estimation<br/>0.10"]
        EN["Environment<br/>0.20"]
        TR["Test Readiness<br/>0.20"]
        DP["Dependency<br/>0.15"]
        OP["Operability<br/>0.07"]
        OB["Observability<br/>0.03"]
    end

    subgraph GATED["12 Gate-Only Assessors — weight=0, CRITICAL/MAJOR risk → verdict cap"]
        direction LR
        G1["Security"]
        G2["Performance"]
        G3["Rollback"]
        G4["Accessibility"]
        G5["Auditability"]
        G6["Disaster Recovery"]
        G7["Data Reconciliation"]
        G8["Failure Mode"]
        G9["Dependency Risk"]
        G10["Production Readiness"]
        G11["Architecture Fitness"]
        G12["Architecture Drift"]
    end

    ORCH --> SCORED
    ORCH --> GATED

    SCORED -.extends.-> BA
    GATED -.extends.-> BA

    subgraph TOOLING["Tool interface — BaseTool Protocol"]
        direction TB
        TRUN["ToolRunner<br/>timeout (threading)<br/>ToolInvocationModel recording"]
        T1["RKTBrainReader<br/>(brain/*.json)"]
        T2["Source readers<br/>(env · dep · operability · observability<br/>rollback · security · performance + 12 others)"]
        TRUN --- T1 & T2
    end

    LLM["LLMProvider (interface)<br/>RuleBased · LocalLLM · Claude<br/>structured output · repair retry · fallback"]

    SCORED --> TRUN
    GATED --> TRUN
    SCORED --> LLM
    GATED --> LLM
    ORCH --> LLM

    classDef orch fill:#e8eaed,stroke:#5f6368;
    classDef abc fill:#f3e8fd,stroke:#7b1fa2;
    classDef scored fill:#e3f2fd,stroke:#1a73e8;
    classDef gated fill:#fce8e6,stroke:#d93025;
    classDef ai fill:#e8f5e9,stroke:#34a853;
    classDef tool fill:#fef7e0,stroke:#f9ab00;
    class ORCH orch;
    class BA,M1,M2,M3,M4 abc;
    class SCORED,SC,ES,EN,TR,DP,OP,OB scored;
    class GATED,G1,G2,G3,G4,G5,G6,G7,G8,G9,G10,G11,G12 gated;
    class LLM ai;
    class TRUN,T1,T2 tool;
```

> **Scored assessors:** weight redistribution applies when a dim is unavailable (ADR-0005) —
> the score stays comparable across runs. Minimum 3 available or verdict = INCOMPLETE.
>
> **Gate-only assessors:** a single CRITICAL risk factor from any gate-only assessor caps the
> verdict at NO_GO regardless of the numeric score (ADR-0013). MAJOR → CONDITIONAL cap.
> Gate-only assessors are all opt-in via `sources.<dim>` config.
