---
description: Start-of-day ritual — orient, prioritize, deep-analyse top tasks with options and outcomes, select the highest-value path
---

Run the full **SOD ritual** for RRR. This is a structured planning session, not just a status read.
Work through all five steps in order and report as you go.

---

## Step 1 — ORIENT: Read current state (≤ 3 sentences)

Read these sources in order:
1. `README.md` → "▶ Next action (start here tomorrow)" pointer
2. Project-state memory (`C:\Users\shri.vallabh\.claude\projects\c--Study-RRR\memory\project-state.md`)
3. Today's date from context

Then run a **quick health check** before proceeding:
- `pytest --co -q | tail -1` — test count vs manifest
- `.venv/Scripts/python.exe scripts/check_comments.py src/rrr` — comment coverage
- `ls adr/*.md | wc -l` (or PowerShell equivalent) — ADR count vs manifest

If `check_comments.py` reports any violations, **surface them before triage** — a COMMENTS: FAIL means a file was edited at some point without running the full gate and needs to be fixed before new work starts.

Output: one paragraph — where the project stands, what milestone is active, what was left pending, and whether the health check found any drift.

---

## Step 2 — TRIAGE: Build a prioritized backlog

Collect pending work from all four sources:
- `docs/roadmap.md` → all `⬜ Planned` and `🔄 In progress` items
- `docs/roadmap.md` → "Design-review actions" table (W1–W6 + Model gap)
- `docs/architecture-review.md` → "Prioritized Remediation Plan" (Quick Wins, Medium-Term, Strategic)
- `README.md` → any items in the living backlog marked `⬜`

Score each item:

```
Priority score = Value(1–5) × Feasibility(1–5) ÷ (1 + unresolved-dependency-count)
```

- **Value**: how directly does this advance the project goal (GO/NO-GO verdict quality, eval proof, demo-readiness)?
- **Feasibility**: can this realistically complete in one focused session?
- **Dependency**: is it blocked by another incomplete item?

Output a ranked table:

| Rank | Item | Category | Value | Feasibility | Deps | Score |
|------|------|----------|-------|-------------|------|-------|

---

## Step 3 — DEEP ANALYSIS: Top 2–3 items

For each of the top 2–3 ranked items, present **three options** — at minimum: a fast path, an alternative path, and explicit defer/skip. Use this structure for every option:

```
### Option [A/B/C]: [Name]
**Outcome:** [Exactly what you will have at the end of the session if you choose this. One sentence.]
**Steps:**
  1. [Concrete action → intermediate output]
  2. ...
**Value delivered:** [FR/NFR/ADR reference that this advances]
**Effort:** [h estimate for a focused session]
**Risk / blocker:** [What could prevent completion or create rework]
```

Sort options within each item by (Outcome value to project goal) descending — Option A is always the highest-value path, Option C is always the defer/skip.

After all options for an item, state:
> **Recommended:** Option [X] because [one-sentence rationale referencing the project goal].

---

## Step 4 — SELECT: Confirm path

Present the top recommendation as:

> **Proposed plan for today:**
> Item [N] — [name], Option [A/B/C]: [outcome sentence]
>
> Proceed with this, or redirect me.

Wait for confirmation before step 5.

---

## Step 5 — IMPACT MAP: Artifact change inventory

Once a path is confirmed (or after presenting the recommendation if the user wants to see it upfront),
produce a checklist of every artifact that will change:

```
### Code
- [ ] src/rrr/<module>/<file>.py — [create / modify: one-line description]

### ADRs
- [ ] adr/NNNN-<title>.md — [create new / add impl-note / update status]

### Documentation
- [ ] docs/roadmap.md — [flip ⬜ → ✅ / ✅ for: item name]
- [ ] docs/architecture.md — [update section: ...]
- [ ] docs/ai-usage.md — [add Stage N entry for: ...]

### Tests
- [ ] tests/unit/test_<file>.py — [create / update]

### Memory
- [ ] project-state memory — [update: ▶ Next action pointer + STATUS line]
```

This checklist becomes the input to `/eod` step 5 (sync all artifacts). If a decision is made
mid-session that changes this list, run `/impact <description of decision>` to regenerate it.

---

Convention details live in the `eod-readme-log` and `project-state` memories. No git, no external
calls — all steps run offline.
