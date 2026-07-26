# 4. Assessor Internals + Guardrail

Inside one assessor: tools produce data, deterministic code produces the **score**,
Claude produces the **judgment**, and the Pydantic guardrail keeps bad generations out
of the pipeline (ADR-0009).

```mermaid
flowchart TB
    START(["evaluate()"]) --> RESET["reset() — clear invocations"]
    RESET --> TOOLS["invoke_tool() via ToolRunner<br/>(timeout + recording)"]
    TOOLS --> TOK{"tools<br/>succeeded?"}

    TOK -- "all fail" --> ZERO["confidence = 0.0<br/>mark INCOMPLETE"]
    ZERO --> RESULT

    TOK -- "some / all ok" --> SCORE["Deterministic score 0.0–1.0<br/>(MAPE / pass-rate / classification)"]
    SCORE --> LLMCALL["reason() via LLMProvider:<br/>classify ambiguous items, extract<br/>risk factors, write evidence narrative"]

    LLMCALL --> PARSE{"structured output<br/>Pydantic valid?<br/>(not refusal)"}
    PARSE -- "valid" --> CONF["calculate_confidence()<br/>(any tool fail ⇒ ≤0.5)"]
    PARSE -- "invalid / refusal" --> REPAIR{"repair retry<br/>(feed error back)"}
    REPAIR -- "now valid" --> CONF
    REPAIR -- "still invalid" --> FALLBACK["fall back to RuleBasedProvider<br/>+ reduced confidence"]
    FALLBACK --> CONF

    CONF --> EVID["build_evidence()<br/>EvidenceRecordModel<br/>(data + tool + LLM invocations)"]
    EVID --> RESULT["DimensionResult<br/>score · confidence · evidence · risk factors"]
    RESULT --> END(["return to Orchestrator"])

    classDef det fill:#e3f2fd,stroke:#1a73e8;
    classDef ai fill:#e8f5e9,stroke:#34a853;
    classDef guard fill:#fce8e6,stroke:#d93025;
    class TOOLS,SCORE,CONF,EVID,FALLBACK det;
    class LLMCALL ai;
    class PARSE,REPAIR guard;
```

**Guardrail summary:** the provider never sets the numeric score or the verdict label; on
validation failure the dimension degrades to the `RuleBasedProvider` rather than emitting
unvalidated data. Works identically whether the provider is rule-based, a local LLM, or Claude.
