---
description: When a design decision requires a new ADR or an update to an existing one
globs: ["adr/*.md"]
---

## When to create a NEW ADR

Create a new ADR in `adr/` before writing code if you are:

- Changing the verdict/scoring algorithm or weight structure (ADR-0006, 0011, 0013 territory)
- Adding a new assessor dimension or changing the assessment model (ADR-0016 territory)
- Adding a new LLM provider or changing the provider interface (ADR-0006)
- Adding any external dependency or network endpoint (ADR-0010)
- Changing how data is persisted or how the schema evolves (ADR-0003)
- Changing the input contract with upstream RKT brain data (ADR-0012)
- Introducing agentic behavior, prompt chaining, or multi-step LLM loops (ADR-0017)
- Centralizing a cross-cutting concern (e.g. the GateEngine — ADR-0014)
- Making a required dimension required-for-GO (ADR-0015)

## When to UPDATE an existing ADR

Add an **implementation note** (do NOT rewrite the decision) when:

- A decision was deferred and is now built — add the implementation date and a one-line note.
- A decision was partially changed in implementation — add a "deviation" section.
- The status changes from Proposed → Accepted, or Accepted → Deprecated.

## ADR format (from adr/0001)

```
# ADR-NNNN: Title
Status: Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
Context: why this decision needed to be made
Decision: what was decided
Consequences: what this enables and what it forecloses
[Implementation note: YYYY-MM-DD — optional, added after build]
```

## Numbering
- Check the highest existing ADR number in `adr/` and increment.
- Run `scripts/check_alignment.py` after creating a new ADR — it asserts the count in CLAUDE.md matches.
