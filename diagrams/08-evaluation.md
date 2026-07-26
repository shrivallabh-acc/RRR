# 8. Evaluation Harness

Offline evaluation (not in the assessment hot path): run RRR on the golden dataset,
compute quantitative metrics deterministically, and score narrative quality with an
LLM-as-judge (ADR-0008, [../docs/evaluation-plan.md](../docs/evaluation-plan.md)).

> **Implementation status (M4 complete):** Golden dataset ✅ (5 fixtures, all `ideal.json` oracles
> authored 2026-06-17). Deterministic metrics ✅ (`tests/eval/metrics.py` — verdict accuracy 100%,
> macro-F1 1.000, all dim MAEs 0.000, mean risk-F1 0.800). `StructuralJudge` ✅ built 2026-06-23
> (`tests/eval/judge.py`) — checks narrative completeness, classification, confidence, rationale,
> risk-factor coverage; structural score 1.00 on all 5 fixtures. `EvalReportRenderer` ✅ built
> 2026-06-23 (`tests/eval/report.py`) — emits `docs/eval-report.md`. `ProseQualityJudge` ✅ built
> 2026-06-26 (`tests/eval/judge.py`) — live-LLM prose scoring via `ClaudeProvider`; API-key guard keeps CI
> offline-safe; eval report §4 added; FR-28 fully closed.

```mermaid
flowchart TB
    subgraph GOLD["Golden dataset (tests/golden/ · 3–5 samples)"]
        G1["g1 clean → GO"]
        G2["g2 failing tests → NO_GO"]
        G3["g3 borderline → CONDITIONAL"]
        G4["g4 missing data → INCOMPLETE"]
        G5["g5 scope creep → CONDITIONAL"]
    end

    GOLD --> RUN["Run RRR on each sample<br/>→ AssessmentOutputModel"]
    RUN --> SPLIT{"compare to ideal.json"}

    SPLIT --> QUANT["Deterministic metrics"]
    QUANT --> M1["Verdict accuracy + macro-F1"]
    QUANT --> M2["Risk-factor precision/recall → F1"]
    QUANT --> M3["Score MAE per dimension"]
    QUANT --> M4["Remediation completeness %"]

    SPLIT --> JUDGE["LLM-as-judge (LLMProvider, local)<br/>faithfulness · completeness · actionability"]

    M1 --> REPORT["Evaluation report<br/>(JSON + Markdown)"]
    M2 --> REPORT
    M3 --> REPORT
    M4 --> REPORT
    JUDGE --> REPORT

    REPORT --> GATE{"thresholds met?<br/>verdict F1 ≥ 0.8 · risk F1 ≥ 0.7<br/>completeness ≥ 0.8 · judge ≥ 0.75"}
    GATE -- "yes" --> PASS["✅ pass"]
    GATE -- "no" --> FAIL["❌ investigate / tune"]

    subgraph PROP["Property tests (Hypothesis) — invariants"]
        P1["score ∈ [0,1]"]
        P2["weights of available dims sum to 1.0"]
        P3["verdict monotonic in score"]
        P4["determinism: same input ⇒ same score+label"]
    end

    classDef ai fill:#e8f5e9,stroke:#34a853;
    classDef det fill:#e3f2fd,stroke:#1a73e8;
    class JUDGE ai;
    class QUANT,M1,M2,M3,M4,P1,P2,P3,P4 det;
```
