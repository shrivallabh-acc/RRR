---
description: Analyse a decision, evaluate options, pick the best, and draft the ADR in Proposed status — heavier-weight than /adr which assumes the decision is already made
---

Perform structured decision analysis for the topic in `$ARGUMENTS`, then write the ADR.

**Key difference from `/adr`:** `/adr` documents a decision already made. `/decide` does the deliberation first — it surfaces options, evaluates each against RRR's constraints, recommends, then drafts the record. Status is always `Proposed` — you review and accept it.

---

## Step 1 — Research

Before analysing options, read:
1. An existing ADR (e.g. `adr/0013-verdict-veto-cap-gates.md`) to match the exact format, tone, and section headings in use.
2. The ADR(s) most relevant to the decision topic — check `adr/` for conflicts.
3. The relevant section of `docs/requirements.md` (FR/NFR references), `docs/architecture.md`, and `docs/roadmap.md` if the decision touches a milestone.
4. Any code in `src/rrr/` that would be directly affected.

Determine the **next sequential ADR number** by listing `adr/` and incrementing the highest number.

## Step 2 — Options table

Produce a table with at least two options (and a "do nothing / defer" option if applicable):

| Option | Summary | Pros | Cons | Fit for RRR |
|--------|---------|------|------|-------------|
| A | | | | |
| B | | | | |
| C — defer/do nothing | | | | |

For each option, explicitly evaluate:
- Does it honour the **local-first / no-external** constraint? (ADR-0010)
- Does it keep the **score deterministic**? (ADR-0006)
- Does it require a **new external dependency**? (flag if yes — native-build risk on Python 3.14)
- Does it **conflict with any existing ADR**? (name the ADR if so)
- What is the **implementation effort** relative to project value?

## Step 3 — Recommendation

State the recommended option in one sentence with a rationale tied to a specific FR/NFR/ADR. Be opinionated — this is decision support, not a neutral summary.

## Step 4 — Write the ADR

Write `adr/NNNN-<kebab-title>.md` in the established project format:

```
# ADR NNNN: <Title>

- **Status:** Proposed
- **Date:** <today YYYY-MM-DD>

## Context
<Why this decision is needed — reference relevant FR/NFR/ADR numbers; 2–4 sentences>

## Decision
<The recommended choice — be specific: what is being done, how, and under what constraints>

## Consequences
<What this enables, what it forecloses, what follow-on work it creates; honest about trade-offs>

## Alternatives Considered
<Brief note on each rejected option and why it was dropped>
```

**Status is always `Proposed`** — never `Accepted` without human sign-off.

## Step 5 — Conflict check

After writing, re-read the ADRs referenced in Step 1 and confirm the new ADR does not silently override any of them. If a conflict exists, add an explicit note in the **Consequences** section: `Supersedes [or amends] ADR-XXXX in the following way: ...`.

## Step 6 — Handoff

Report:
- The ADR file written (`adr/NNNN-<title>.md`)
- Whether `docs/roadmap.md` or `docs/architecture.md` should reference the new ADR
- Whether the alignment script (`scripts/check_alignment.py`) will need its ADR count updated after this is accepted
