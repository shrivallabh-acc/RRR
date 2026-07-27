# Tests

766 tests across four suites. All four must pass before any work is considered complete.

---

## Running tests

```powershell
# Full suite
.venv\Scripts\python.exe -m pytest

# Fast — unit tests only
.venv\Scripts\python.exe -m pytest tests/unit/

# Golden fixture E2E
.venv\Scripts\python.exe -m pytest tests/golden/

# Property tests (Hypothesis)
.venv\Scripts\python.exe -m pytest tests/property/

# Single module
.venv\Scripts\python.exe -m pytest tests/unit/test_scope_assessor.py

# Skip the LLM eval harness (slow, needs a provider)
.venv\Scripts\python.exe -m pytest -m "not eval"

# Verbose output
.venv\Scripts\python.exe -m pytest -v
```

---

## Suite overview

### `unit/`

42 test files — one per source module. Each test file:
- Tests the module in isolation (mocks external I/O: file reads, API calls, LLM calls).
- Never mocks the deterministic math — assessor score computation is always tested
  against real `InputContract` data.
- Runs in < 1 second per file.

Key files:
| File | What it covers |
|---|---|
| `test_scope_assessor.py` | ScopeAssessor score/risk/confidence |
| `test_test_readiness_assessor.py` | E2E pass rate gates, freshness |
| `test_environment_assessor.py` | Provisioning, stability grades |
| `test_dependency_assessor.py` | Integration status, blocking deps |
| `test_scoring.py` | Weight redistribution, split scores |
| `test_verdict.py` | Gate caps, band boundaries, INCOMPLETE |
| `test_persistence.py` | SQLite WAL mode, migration guard, Chroma |
| `test_config.py` | Env-var interpolation, deep merge |
| `test_collectors.py` | CollectorRunner status and run paths |
| `test_ui_helpers.py` | Pure dashboard data helpers |

### `property/`

Hypothesis-based invariant tests in `test_scoring_properties.py`.

The following invariants are verified for all valid input combinations:

| Invariant | Description |
|---|---|
| Score bounds | Score is always in [0.0, 1.0] |
| Weight normalisation | Redistributed weights sum to 1.0 |
| Verdict determinism | Same inputs always produce the same verdict |
| INCOMPLETE condition | Verdict is INCOMPLETE iff available dims < `minimum_assessors` |
| CRITICAL gate | CRITICAL risk factor always produces NO_GO |
| Band monotonicity | Higher score → verdict label ≥ lower score label |

### `golden/`

Five end-to-end fixtures that run the full pipeline against realistic input data.

| Fixture | Verdict | Score | Notes |
|---|---|---|---|
| `g1_clean_release` | GO | 97 | All green, high confidence |
| `g2_blocked_release` | NO_GO | — | Blocker defects + failed environment |
| `g3_marginal_release` | CONDITIONAL | 74 | Borderline E2E, MAJOR risk factors |
| `g4_incomplete_release` | INCOMPLETE | — | Too few assessors available |
| `g5_conditional_release` | CONDITIONAL | 93 | Gate cap from security dimension |

Each fixture directory contains:
- `inputs/` — brain JSON, dimension JSON files, config YAML
- `ideal.json` — the oracle result (verdict, score, expected dimensions)

Tests assert against `ideal.json`. If you change scoring, update the oracle first.

### `eval/`

LLM evaluation harness (FR-28, ADR-0008). Not run in standard CI — requires a live
provider.

- `StructuralJudge` — validates narrative structure (contains evidence, avoids
  hallucination, respects the label space).
- `ProseQualityJudge` — LLM-as-judge scoring of rationale quality.

Run with: `pytest tests/eval/ -m eval`

### `fixtures/`

Mock LLM response JSON files used by `MockLLMProvider` in unit and golden tests.

---

## Coverage requirements by layer

| Layer | Required tests | Location |
|---|---|---|
| New assessor | Unit vs ≥ 1 golden fixture | `tests/unit/test_<dim>_assessor.py` |
| New provider | Unit: normal + repair + fallback | `tests/unit/test_<provider>.py` |
| New model | Unit: valid construction + validator rejection | `tests/unit/test_models.py` |
| New tool | Unit: success + timeout + invocation recording | `tests/unit/test_tools.py` |
| Scoring change | Property: update `tests/property/test_scoring_properties.py` | Hypothesis |
| New gate rule | E2E: verify golden fixture verdict still holds | `tests/unit/test_orchestrator.py` |

See [.claude/rules/test-coverage.md](../.claude/rules/test-coverage.md) for the full
coverage policy.
