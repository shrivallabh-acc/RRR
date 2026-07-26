---
description: Enforce the BaseAssessor template-method pattern for all assessor implementations
globs: ["src/rrr/assessors/*.py"]
---

When creating or modifying any file in `src/rrr/assessors/`:

## Required structure

- Every assessor MUST extend `BaseAssessor` — never implement the `assess()` orchestration directly.
- The `_assess()` method MUST return `DeterministicAssessment` — it owns ALL numeric computation.
- The score MUST be computed from deterministic math (thresholds, ratios, weights) — never from provider output.
- Risk factors MUST be assigned severity explicitly (`CRITICAL` / `MAJOR` / `MINOR`) — the gate engine reads these directly (ADR-0013).
- All tool calls MUST go through `self.invoke_tool()` for audit recording — never call a tool directly.
- Never call `self.provider` or `self.reason()` from within `_assess()` — the base class calls `reason()` after `_assess()` returns.

## Severity → gate mapping (ADR-0013)
- `CRITICAL` risk factor → NO_GO cap
- `MAJOR` risk factor → CONDITIONAL cap
- `MINOR` risk factor → no gate effect

## Confidence rules (FR-12)
- Low data quality or missing required fields → reduce confidence, do not inflate score.
- If a required input is absent, emit a CRITICAL risk factor and apply `confidence_cap` in `DeterministicAssessment`.

## Tests
- Add `tests/unit/test_<dimension>_assessor.py` verified against at least one golden fixture from `tests/golden/`.
- Run `pytest tests/unit/test_<dimension>_assessor.py` before marking the work complete.
- Property tests for new scoring invariants belong in `tests/property/test_scoring_properties.py`.
