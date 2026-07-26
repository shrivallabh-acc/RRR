---
description: Enforce Pydantic v2 model conventions for all data models
globs: ["src/rrr/models/*.py"]
---

When creating or modifying any file in `src/rrr/models/`:

## Two model postures (do not mix)

| Posture | Base | Config | Use for |
|---------|------|--------|---------|
| Output / value object | `RRRModel` (frozen, `extra=forbid`) | immutable | `DimensionResult`, `AssessmentOutputModel`, LLM I/O |
| Input contract | `InputContract` (`extra=ignore`) | mutable | Brain/env/dep upstream data — tolerate unknown fields |

- Never use a raw `dict` to carry data across module boundaries — use a typed model.
- Never use `extra=allow` on output models — the schema must be closed.

## Field requirements
- All fields MUST have explicit type annotations.
- All fields MUST have `Field(description="…")` — the description becomes the LLM prompt context.
- Cross-field constraints MUST use `@model_validator(mode='after')`.
- Enums belong in `models/enums.py`, not inline in individual model files.

## Naming
- Output models use the `…Model` suffix (e.g. `DimensionResultModel` → `DimensionResult` is the alias).
- LLM I/O models use `…Request` / `…Response` suffixes.

## After any model change
- Run `mypy src` — strict typing is required (NFR-5). A model change that breaks mypy is not complete.
- If the change alters a field used in golden fixtures, update the fixture and re-run the affected tests.
