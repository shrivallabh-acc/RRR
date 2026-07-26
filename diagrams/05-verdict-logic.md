# 5. Verdict & Scoring Logic

How the orchestrator turns 5 `DimensionResult`s into a verdict — including weight
redistribution for unavailable dimensions and the score → label mapping.

```mermaid
flowchart TB
    START(["fan-in: 5 DimensionResults"]) --> COUNT{"succeeded ≥<br/>minimum_assessors<br/>(default 3)?"}
    COUNT -- "no" --> INC["Verdict = INCOMPLETE"]
    COUNT -- "yes" --> REDIST["Redistribute weight of any<br/>unavailable dimension equally<br/>among available dimensions"]

    REDIST --> SUM["score = Σ (weightᵢ × dimension_scoreᵢ)<br/>over available dimensions"]
    SUM --> RISK["Apply risk-acceptance<br/>adjustment (proportional)"]
    RISK --> MAP{"score range?"}

    MAP -- "≥ 0.80" --> GO["Verdict = GO"]
    MAP -- "< 0.40" --> NOGO["Verdict = NO_GO"]
    MAP -- "0.40 – 0.80" --> COND["Verdict = CONDITIONAL"]

    GO --> RAT
    NOGO --> RAT
    COND --> RAT
    INC --> RAT["LLMProvider synthesizes rationale<br/>+ remediation (RAG-grounded,<br/>schema-validated)"]
    RAT --> EXIT["Exit code: GO=0 · NO_GO=1<br/>CONDITIONAL=2 · ERROR=3"]
    EXIT --> END(["AssessmentOutputModel"])

    classDef det fill:#e3f2fd,stroke:#1a73e8;
    classDef ai fill:#e8f5e9,stroke:#34a853;
    classDef verdict fill:#fef7e0,stroke:#f9ab00;
    class REDIST,SUM,RISK,EXIT det;
    class RAT ai;
    class GO,NOGO,COND,INC verdict;
```

> The verdict **label is a pure function of the numeric score** (and assessor count) —
> never of free-form LLM text. This is what keeps the verdict reproducible.
