---
description: Enforce the deterministic-first principle across all RRR source code
globs: ["src/rrr/**/*.py"]
---

This is the most important architectural invariant in RRR (ADR-0006, ADR-0009).

## The line that must never be crossed

```
DETERMINISTIC (always code)          │  LLM (always provider, always validated)
─────────────────────────────────────┼──────────────────────────────────────────
Numeric score computation            │  Dimension narrative (evidence prose)
Risk factor extraction               │  Verdict rationale synthesis
Weight redistribution                │  Remediation plan generation
Verdict derivation (score → label)   │  Ambiguous-item classification
Config/output validation             │  (nothing else)
SQLite persistence                   │
Trend computation                    │
```

## Concrete checks — ask yourself before committing

1. Does any LLM response influence a numeric score? → **NO. Never.**
2. Does the verdict label come from LLM output or from the score band? → **Score band only.**
3. Is there raw LLM text crossing a module boundary without Pydantic validation? → **No.**
4. Does a new code path make an external network call? → **Only if the host is in the allow-list (ADR-0010).**
5. Is there a prompt chain (output of one LLM call fed as instruction to another)? → **Needs a new ADR.**

## Weight redistribution rule (ADR-0005)
- If a dimension is unavailable, redistribute its weight proportionally across available dimensions.
- This is pure math — no LLM involvement.
- Minimum assessors threshold (default 3) must be met or verdict is `INCOMPLETE`.

## Gate rule (ADR-0013)
- `CRITICAL` risk factor → `NO_GO` cap on verdict.
- `MAJOR` risk factor → `CONDITIONAL` cap.
- Gate application is deterministic code in `orchestration/verdict.py` — never in a provider.
