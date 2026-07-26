# Diagrams — Release Readiness Results (RRR)

Diagrams-as-code in **Mermaid** — they render natively on GitHub and in VS Code
(install the "Markdown Preview Mermaid Support" extension) and stay diffable in version
control. Together they document the design: **agent roles, tool interfaces, memory
structure, interactions, and trace paths.**

| # | Diagram | Shows |
|---|---------|-------|
| 1 | [System architecture](01-system-architecture.md) | End-to-end components: inputs → config → orchestrator → assessors → LLM → memory → output |
| 2 | [Agent roles & tool interfaces](02-agent-roles.md) | Orchestrator + 5 assessor agents, the `BaseTool`/`ToolRunner` surface, `LLMProvider` |
| 3 | [Assessment sequence](03-assessment-sequence.md) | Runtime interactions over time (fan-out/fan-in, RAG, verdict synthesis) |
| 4 | [Assessor internals + guardrail](04-assessor-internals.md) | Deterministic score + Claude reasoning + Pydantic guardrail / repair / degrade |
| 5 | [Verdict & scoring logic](05-verdict-logic.md) | Weight redistribution and GO/NO-GO/CONDITIONAL/INCOMPLETE mapping |
| 6 | [Memory & RAG](06-memory-rag.md) | SQLite (canonical) + Chroma (vector) and the RAG benchmark loop |
| 7 | [Audit trail / trace path](07-audit-trail.md) | Chain of evidence: verdict → scores → evidence → tool & LLM invocations |
| 8 | [Evaluation harness](08-evaluation.md) | Golden dataset → metrics (F1) + LLM-as-judge → report |
| 9 | [Deployment (local-first)](09-deployment.md) | Phase-1 on-machine boundary vs. Phase-2 external scale-out, behind one interface |

> **Export to PNG/SVG** with the Mermaid CLI:
> `npx -p @mermaid-js/mermaid-cli mmdc -i 01-system-architecture.md -o 01-system-architecture.svg`
