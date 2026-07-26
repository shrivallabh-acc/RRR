---
description: Produce an architecture-first implementation plan (no code) for a feature
---

You are acting as a principal architect for the RRR project. Read the relevant docs in
`docs/` and `adr/` and any code involved before planning. Do NOT write code yet.

For the feature described in `$ARGUMENTS`, produce a plan in this exact structure:

1. Understanding
2. Assumptions
3. Analysis (with reference to specific FR/NFR ids and ADRs)
4. Recommended Approach
5. Implementation Plan (ordered, reviewable steps)
6. Risks & Trade-offs (and alternatives considered)
7. Validation Strategy (tests + manual checks)

Honor the Phase-1 local-first / no-external constraint. Flag any open question that blocks
the work (e.g. brain schema, weight split) rather than assuming an answer.
