# 7. Audit Trail / Trace Path

The chain of evidence: every conclusion is navigable back to the data and the exact
tool/LLM calls that produced it. ISO 8601 millisecond timestamps throughout.

```mermaid
flowchart TD
    V["VERDICT: e.g. CONDITIONAL<br/>score 0.62 · schema_version 1.0.0"]

    V --> D1["Scope — 0.88"]
    V --> D2["Estimation — 0.71"]
    V --> D3["Environment — 0.40"]
    V --> D4["Test Readiness — 0.55"]
    V --> D5["Dependency — 0.60"]
    V --> RAT["Verdict rationale + remediation<br/>(LLM, RAG-grounded)"]

    D3 --> E3["EvidenceRecordModel<br/>confidence 0.5 · risk: 1 component down"]
    E3 --> TI1["ToolInvocationModel<br/>ComponentStatusTool<br/>params · output ≤500 chars<br/>success · duration_ms"]
    E3 --> LI1["LLM invocation<br/>model · prompt ref · tokens<br/>structured output (validated)"]

    RAT --> RAG["RAG sources<br/>(similar prior releases)"]
    RAT --> LI2["LLM invocation<br/>verdict synthesis"]

    classDef verdict fill:#fef7e0,stroke:#f9ab00;
    classDef dim fill:#e3f2fd,stroke:#1a73e8;
    classDef ev fill:#e8eaed,stroke:#5f6368;
    classDef ai fill:#e8f5e9,stroke:#34a853;
    class V verdict;
    class D1,D2,D3,D4,D5 dim;
    class E3,TI1 ev;
    class RAT,LI1,LI2,RAG ai;
```

**Navigation:** `verdict → dimension scores → evidence records → tool invocations + LLM
invocations`. Each LLM invocation logs model, prompt reference, token usage, and the
validated structured output — so "why this verdict?" is fully answerable offline.
