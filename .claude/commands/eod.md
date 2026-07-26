---
description: Run the end-of-day ritual — gate, alignment check, dated log entry, next-action pointer, and full artifact sync
---

Run the full **EOD ritual** for RRR. This is the daily project-sync, not just a log append — every
artifact must end the day aligned with what was actually built. Do all steps in order; report as you go.

1. **Quality gate** — run all four in order via `.venv/Scripts/python.exe`:
   `scripts/check_comments.py src/rrr`, `ruff check src tests`, `mypy src`, `pytest`.
   Capture the test count. All four must be green before logging. If anything fails, fix it first.

2. **Alignment check** — run `.venv/Scripts/python.exe scripts/check_alignment.py`.
   It must print `ALIGNMENT: PASS`. If it FAILs, **fix the drift in the docs first**, then re-run
   until it passes. Common drift: ADR count in docs, stale "deferred" status headers, diagram impl
   notes claiming features are unbuilt.

3. **Daily log entry** — in `README.md` → "Daily Progress Log (EOD)", add today's dated entry at the
   top (extend it if the date already exists). Three buckets — **Planned · Completed · Pending/next**
   (concise, 1–3 bullets, carry unfinished items forward) — plus a final **metrics line**:
   `_Metrics: NNN tests · comments+ruff+mypy+pytest green · alignment PASS · roadmap <state>_`.
   Flip finished items in the living backlog ✅ and update the milestone table if a milestone changed.
   Bump the "_last updated_" date in the Status heading.

4. **▶ Next action** — overwrite the single "▶ Next action (start here tomorrow)" pointer near the top
   of the log with the **exact next concrete step** (file / function / decision) so tomorrow starts
   with zero re-derivation. Mirror it in the `project-state` memory.

5. **Full file sweep — every status-bearing file, no exceptions.**

   Walk every file in the list below and verify it matches current reality. **Do not skip a file
   because "nothing changed there today."** Stale content accumulates in files that weren't touched
   — checking only changed files is what caused the drift. Fix every mismatch found before closing.

   ### Single-source-of-truth counts (read from step 2 output)
   - [ ] `CLAUDE.md` — test count in "Current status", tech stack (built vs. planned), milestone state
   - [ ] `README.md` — status heading date, test count, milestone table rows, M1 backlog ✅/⬜, ▶ Next action
   - [ ] `.claude/artifact-manifest.md` — State variables table: test count, M2/M4/M5 status, ADR-0014/0015 status, ▶ Next action row

   ### ADRs (every `adr/*.md` file — all 17)
   - [ ] `adr/CLAUDE.md` — ADR count (must match `check_alignment.py` output), proposed ADRs section (status must be accurate)
   - [ ] Each `adr/0*.md` — **Status header**: if the file has an "Implementation Note" with "Built", the Status line must say "Accepted (implemented YYYY-MM-DD)", NOT "deferred". Check every ADR, not just ones touched today.

   ### Docs (every `docs/*.md` file)
   - [ ] `docs/architecture.md` — implementation status banner: test count, what's built vs. not yet built
   - [ ] `docs/roadmap.md` — milestone table rows (✅/🔄/⬜), M2/M3/M4 work breakdown checkboxes
   - [ ] `docs/architecture-review.md` — Finding resolution statuses (✅ RESOLVED / open)
   - [ ] `docs/ai-usage.md` — add a Stage entry for today's work (append; never rewrite historical entries)
   - [ ] `docs/enterprise-deployment.md` — check if any referenced capabilities or commands changed
   - [ ] `docs/vision.md`, `docs/requirements.md`, `docs/evaluation-plan.md` — generally stable; scan for any "not yet built" / "planned" claims that are now complete

   ### Diagrams (every `diagrams/*.md` file — all 9)
   - [ ] Each `diagrams/NN-*.md` — implementation note block: nothing says "not yet built" or "planned wrapper" for a feature that IS built. Key: LangGraph ✅ (built 2026-06-20), Chroma RAG ✅ (built 2026-06-19).

   ### Scoped CLAUDE.md files
   - [ ] `src/rrr/orchestration/CLAUDE.md` — LangGraph entry point, gate engine status
   - [ ] `adr/CLAUDE.md` — (covered above)

   ### Memory
   - [ ] `memory/project-state.md` — STATUS line (date + test count), ▶ NEXT ACTION, latest "Built (YYYY-MM-DD additions)" paragraph

   After all updates: re-run step 2 (`scripts/check_alignment.py`) to confirm still `ALIGNMENT: PASS`.

Convention details live in the `eod-readme-log` memory. Note: the user declined git, so do **not**
suggest version control or rely on `git` for any step.
