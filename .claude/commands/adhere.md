---
description: Spot-check recently modified files against the six core project rules — reports violations, does not fix
---

Perform a READ-ONLY compliance spot-check. Report findings concisely; do not fix anything.

---

## The six rules

| # | Rule | Source |
|---|------|--------|
| 1 | **Architecture first** — no jumping to code without understanding context, domain, and trade-offs | `.claude/project-context.md` |
| 2 | **Strong typing** — all public functions type-hinted; Pydantic v2 models with `Field` + validators; `mypy --strict` must pass | NFR-5 |
| 3 | **Local-first / no external** — no outbound network calls at runtime in Phase 1; non-localhost hosts rejected by `ConfigLoader` | ADR-0010 |
| 4 | **Deterministic score** — LLM writes rationale/classification only; verdict label derives from numeric score, never from provider output | ADR-0006, ADR-0009 |
| 5 | **Graceful degradation** — system still produces a verdict if ≥ `minimum_assessors` (default 3) dimensions succeed; weight redistributes | ADR-0005 |
| 6 | **ADR for significant decisions** — new design decisions, deviations, or reversals of prior decisions go in `adr/` before the code lands | ADR-0001 |

---

## How to run

1. **Identify files to check** — use files you wrote or edited in this session (check conversation history). If session context is unavailable, list the 10 most recently modified `.py` files in `src/` and `tests/`.

2. **For each file, check each rule:**

   | Rule | What to look for |
   |------|-----------------|
   | 1 Architecture first | Was this file created/changed without first reading the relevant ADRs and docs? Flag if the change looks like a direct jump to implementation. |
   | 2 Strong typing | Any function missing return type or parameter types? Any model field without `Field()`? Any `Any` type that could be narrowed? |
   | 3 Local-first | Any `import requests`, `import httpx`, `urllib`, or direct socket calls? Any hardcoded URL that isn't `127.0.0.1`/`localhost`? |
   | 4 Deterministic score | In assessors: does `_assess()` compute the score from math, or does it use provider output for the number? In orchestration: does verdict derive from the score band, not from LLM text? |
   | 5 Graceful degradation | In assessors: does a tool failure propagate unhandled? Does the orchestrator handle a dimension being unavailable by redistributing weight? |
   | 6 ADR coverage | Does the change introduce a new pattern, override a prior decision, or add an external dependency? If so, is there a matching ADR in `adr/`? |

3. **Output format** — for each finding:

   ```
   FILE: src/rrr/<module>/<file>.py
   RULE: [N] <rule name>
   FINDING: <one sentence — what specifically was observed and why it's a concern>
   SEVERITY: BLOCK | WARN
   ```

   - **BLOCK** — clear violation that contradicts a hard constraint (ADR-0009/0010/0006) or breaks the type contract
   - **WARN** — potential concern or pattern that should be reviewed before merging

4. **Summary line** at the end:
   ```
   RESULT: N BLOCK(s), N WARN(s) across N file(s)
   ```
   If no findings: `RESULT: CLEAN — no violations found`

---

This command is read-only. It reports, it does not modify files.
