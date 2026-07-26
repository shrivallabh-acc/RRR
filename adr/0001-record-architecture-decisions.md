# ADR 0001: Record Architecture Decisions

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
We need to capture significant architectural decisions, the context behind them,
and their consequences, so future contributors understand why the system is the
way it is.

## Decision
We will use Architecture Decision Records (ADRs). Each decision is a numbered
Markdown file in this `adr/` directory, following this template.

## Consequences
- Decisions are versioned alongside the code.
- New ADRs supersede older ones rather than editing history; mark superseded ADRs accordingly.

---

## ADR Template
```
# ADR NNNN: <title>

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD

## Context
## Decision
## Consequences
```
