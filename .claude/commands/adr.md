---
description: Draft a new Architecture Decision Record in the project's established format
---

Create a new ADR for the decision described in `$ARGUMENTS`.

1. Read an existing ADR in `adr/` (e.g. `adr/0002-langgraph-for-orchestration.md`) to match the
   exact format, tone, and section headings already in use.
2. Determine the next sequential number from the files in `adr/`.
3. Write `adr/NNNN-<kebab-title>.md` following that format. Include Status, Context, Decision,
   Consequences, and Alternatives Considered.
4. Keep it consistent with existing decisions — flag any conflict with a prior ADR instead of
   silently contradicting it.
5. Note in your reply whether `docs/roadmap.md` or `docs/architecture.md` should be updated to
   reference the new ADR.
