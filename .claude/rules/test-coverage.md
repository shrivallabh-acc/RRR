---
description: Test coverage requirements for new and modified source files
globs: ["tests/**/*.py"]
---

## Coverage requirements by layer

| Layer | Required tests | Location |
|-------|---------------|----------|
| New assessor | Unit tests vs ≥1 golden fixture | `tests/unit/test_<dim>_assessor.py` |
| New provider | Unit: normal + repair + fallback paths | `tests/unit/test_<provider>.py` |
| New model | Unit: valid construction + validator rejection | `tests/unit/test_models.py` |
| New tool | Unit: success + timeout + invocation recording | `tests/unit/test_tools.py` |
| Scoring change | Property: update `tests/property/test_scoring_properties.py` | Hypothesis |
| New gate rule | End-to-end: verify golden fixture verdict still holds | `tests/unit/test_orchestrator.py` |

## Golden fixtures as the ground truth

- Tests MUST assert against real golden fixture data (`tests/golden/g*/`), not fabricated dicts.
- `ideal.json` in each fixture is the oracle — if you change scoring, update the oracle first, then the test.
- Never mock the assessor math — mock only external I/O (file reads, API calls) when unavoidable.

## Before marking work complete

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_<relevant_file>.py  # fast, targeted
.venv/Scripts/python.exe -m pytest                                       # full suite
.venv/Scripts/python.exe -m mypy src                                     # type-check
.venv/Scripts/python.exe -m ruff check src tests                         # lint
```

All four must be green. Never claim "tests pass" without running them.

## Property test invariants to preserve (Hypothesis)
- Score is always in [0.0, 1.0]
- Weight normalization: redistributed weights sum to 1.0
- Verdict is deterministic for the same inputs
- INCOMPLETE iff available dimensions < `minimum_assessors`
- CRITICAL risk factor always produces NO_GO (not CONDITIONAL or GO)
- Band monotonicity: higher score → verdict label ≥ lower score label
