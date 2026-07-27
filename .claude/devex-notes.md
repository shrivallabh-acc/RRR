# Claude Code Prompt — RRR Developer Experience Improvements

> Copy this entire prompt into Claude Code in VS Code. Execute in one session.
> Estimated time: ~90 minutes for all 4 items.
> Project: RRR (C:\Study\RRR)

---

## Context

You are working on the RRR project — an AI-first, local-first Python CLI for release readiness assessment. The dev environment is VS Code + Claude Code on Windows. Python 3.14, `.venv/` at project root, tools run as `.venv/Scripts/python.exe -m <tool>`.

Read `CLAUDE.md` and `.claude/project-context.md` before starting. The architecture review (`docs/architecture-review.md`) identified these as quick wins for developer experience. Implement all four in order.

---

## Task 1: Post-File-Write Hook — Ruff on Save (15 min)

**Goal:** Add a Claude Code hook in `.claude/settings.json` that automatically runs `ruff check` on any `.py` file after it's written. This catches lint errors at write time instead of waiting for `/check`.

**Requirements:**
- Add a `postFileWrite` hook entry to `.claude/settings.json` (NOT a separate hook file — this goes in the existing settings)
- Pattern: `"*.py"` files only
- Command: `.venv/Scripts/ruff check {file}` (Windows path, uses the project venv)
- If ruff reports errors, surface them in the Claude Code output so I see them immediately
- Do NOT run ruff on non-Python files
- Do NOT add formatting (ruff format) — just the lint check

**Reference:** Current `.claude/settings.json` has `permissions.allow` with `"Bash(ruff:*)"` already permitted.

**Deliverable:** Updated `.claude/settings.json` with the hook added.

---

## Task 2: Makefile (30 min)

**Goal:** Create a `Makefile` at project root so `make check` runs the full quality gate in one command.

**Requirements:**
- Must work on Windows with `make` (GNU Make for Windows) OR provide a `make.ps1` PowerShell equivalent alongside it
- Targets:
  - `lint` — `ruff check src tests && ruff format --check src tests`
  - `type` — `mypy src`
  - `test` — `pytest`
  - `check` — runs `lint`, then `type`, then `test` (in that order, fail-fast)
  - `fix` — `ruff format src tests && ruff check --fix src tests` (auto-fix)
  - `all` — alias for `check`
- All commands must use the `.venv` Python (`.venv/Scripts/python.exe -m pytest`, etc.) since we're on Windows without activation
- Add a `.PHONY` declaration for all targets
- Add a brief comment header explaining what this is

**Deliverable:** `Makefile` at project root. Optionally `make.ps1` for PowerShell-native usage.

---

## Task 3: `/adhere` Command (20 min)

**Goal:** Create a Claude Code slash command at `.claude/commands/adhere.md` that performs a spot-check of recently modified files against the project's six core rules.

**The six rules** (from `.claude/project-context.md` and `CLAUDE.md`):
1. **Architecture first** — no jumping to code without understanding context, domain, trade-offs
2. **Strong typing** — all public functions type-hinted, Pydantic v2 models with Field + validators (NFR-5)
3. **Local-first / no external** — no outbound network calls at runtime in Phase 1 (ADR-0010)
4. **Deterministic score** — LLM writes rationale only, verdict label derives from numeric score (ADR-0006/0009)
5. **Graceful degradation** — system still produces a verdict if components fail (ADR-0005)
6. **ADR for decisions** — significant architectural choices get an ADR in `adr/` (ADR-0001)

**Requirements:**
- The command takes no arguments
- It should:
  1. List the six rules (one line each)
  2. Identify files modified in the current session (or fall back to `git diff --name-only` if session info unavailable)
  3. For each modified file, check whether it potentially violates any of the six rules
  4. Report: file name, rule potentially violated, brief explanation
  5. If no violations found, say so clearly
- Output format: concise, actionable, no fluff
- This is a READ-ONLY command — it reports, it does not fix

**Deliverable:** `.claude/commands/adhere.md`

---

## Task 4: `/decide` Skill (30 min)

**Goal:** Create a Claude Code slash command at `.claude/commands/decide.md` that takes a decision topic and produces a structured ADR-ready decision record. This is the complement to a hypothetical `/grill-me` (which asks questions one at a time). `/decide` is synthesis-mode: given analysis already done, it produces the decision artifact.

**Requirements:**
- Takes `$ARGUMENTS` — a description of the decision to be made
- Before writing, it must:
  1. Read an existing ADR from `adr/` to match the established format
  2. Read relevant docs/code if the decision references existing components
  3. Determine the next sequential ADR number
- Output structure (matching existing ADR format):
  ```
  # ADR NNNN: <Title>
  - Status: Proposed (not Accepted — human reviews first)
  - Date: <today>
  
  ## Context
  <Why this decision is needed — reference relevant FRs/NFRs/ADRs>
  
  ## Options Considered
  | Option | Pros | Cons | Fit for RRR |
  |--------|------|------|-------------|
  | A | ... | ... | ... |
  | B | ... | ... | ... |
  
  ## Decision
  <The recommended choice with reasoning>
  
  ## Consequences
  <What changes, what's affected, what's the trade-off accepted>
  
  ## Alternatives Rejected
  <Brief note on why each non-chosen option was dropped>
  ```
- Status is always "Proposed" — never "Accepted" without human sign-off
- The command should flag if the decision conflicts with any existing ADR
- Write the file to `adr/NNNN-<kebab-title>.md`

**Key difference from the existing `/adr` command:** `/adr` assumes a decision is already made and just documents it. `/decide` does the analysis — it evaluates options, recommends, and produces the record in one pass. It's heavier-weight and more opinionated.

**Deliverable:** `.claude/commands/decide.md`

---

## Execution Notes

- Do each task in order. After each task, run the relevant validation:
  - Task 1: Confirm `.claude/settings.json` is valid JSON
  - Task 2: Run `make check` (or equivalent) and confirm it executes
  - Task 3: Confirm `.claude/commands/adhere.md` parses correctly (has the `---` frontmatter)
  - Task 4: Confirm `.claude/commands/decide.md` has frontmatter and references the existing ADR format
- Do not modify any existing source code in `src/` or `tests/`
- Do not modify `CLAUDE.md` or `.claude/project-context.md`
- All new files should follow existing project conventions (check existing files in `.claude/commands/` for format)
