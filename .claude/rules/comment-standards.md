# Comment Standards — RRR

Every file in `src/rrr/` must meet the standards below before a change is considered
complete. Run the linter to verify: `python scripts/check_comments.py src/rrr`.

---

## What must be commented

### 1 — Every module
Every `.py` file must start with a module docstring (triple-quoted string, first
statement after imports). It must explain:
- **What this module does** (one sentence)
- **Why it exists** in the architecture (ADR/FR reference if relevant)
- **How it connects** to the rest of the system (what calls it, what it calls)

**Bad:**
```python
# scoring module
from rrr.models.dimension import DimensionResult
```

**Good:**
```python
"""Weighted scoring with redistribution for unavailable dimensions (FR-7).

Only available dimensions contribute. Unavailable dimension weight is spread
proportionally across available ones so the score stays comparable (ADR-0005).
"""
```

---

### 2 — Every class
Every `class` must have a one-line docstring at minimum. Explain the class's role,
not just its name. For data models, explain what it represents and when it is created.

**Bad:**
```python
class GateEngine:
    pass
```

**Good:**
```python
class GateEngine:
    """Maps risk factors to verdict caps using named config gates or severity fallback."""
```

---

### 3 — Every public method and function
Every `def` that is not a one-liner property must have a docstring. It must explain:
- **What the function does** (the business purpose, not just the mechanic)
- **Parameters** — if non-obvious (what units? what shape?)
- **Return value** — if non-obvious
- **Errors raised** — if the caller needs to handle them

**Bad:**
```python
def assess(self) -> DimensionResult:
    self.reset()
    ...
```

**Good:**
```python
def assess(self) -> DimensionResult:
    """Run the full pipeline and return this dimension's DimensionResult.

    Calls _assess() for the deterministic part, then asks the provider to write
    the narrative, then computes confidence from tool outcomes (FR-12).
    On ToolError the dimension is marked unavailable rather than crashing.
    """
```

---

### 4 — Every private / static helper method
Private methods (`_name`) and static helpers must also have docstrings. These are
the methods a junior developer is most likely to misunderstand. Explain the WHY, not
just the WHAT.

**Bad:**
```python
@staticmethod
def _classify(completion: float) -> ScopeClass:
    if completion >= DELIVERED_THRESHOLD:
        return ScopeClass.DELIVERED
```

**Good:**
```python
@staticmethod
def _classify(completion: float) -> ScopeClass:
    """Map a 0-1 completion ratio to a delivery class.

    DELIVERED means 90%+ of planned story points are closed — good enough to
    ship. PARTIALLY_DELIVERED is the amber zone (50-90%). NOT_DELIVERED means
    fewer than half the points are done — a release would be very high risk.
    """
```

---

### 5 — Non-obvious inline logic
Add a `#` comment above (or at the end of) any line where the reason is not obvious
from the code alone. This includes:
- Magic thresholds or constants (explain what they represent)
- Guard clauses (explain what you're guarding against)
- Algorithm steps that need context
- Deliberate workarounds or edge-case handling

**Bad:**
```python
confidence = min(confidence, _CONFIDENCE_CAP_ON_FAILURE)
```

**Good:**
```python
# Degraded reasoning reduces trust in the result even if tools succeeded.
confidence = min(confidence, _CONFIDENCE_CAP_ON_FAILURE)
```

---

### 6 — Error handling blocks
Every `except` block must have a comment explaining:
- What kind of failure this catches
- Why we handle it this way (rather than letting it propagate)

**Bad:**
```python
except urllib.error.URLError as exc:
    raise ProviderValidationError(...)
```

**Good:**
```python
except (urllib.error.URLError, OSError) as exc:
    # Connection refused, DNS failure, socket timeout, etc.
    # Re-raise as ProviderValidationError so the fallback path handles it
    # identically to a structured-output validation failure.
    raise ProviderValidationError(...)
```

---

## Comment style rules

| Rule | Good | Bad |
|------|------|-----|
| Plain English | "Skip if no prior data." | "Predicate evaluation gate for temporal antecedent nullity." |
| Explain WHY | "ISO dates sort as strings — no parsing needed." | "Sorts by date string." |
| No obvious comments | (none) | `# Increment counter` above `count += 1` |
| No stale references | (no mentions of PR numbers, caller names) | `# Added for ADR-0013 fix in PR #42` |
| Assume junior reader | Full sentences, no unexplained abbreviations | Single cryptic words |

---

## What does NOT need a comment

- Simple one-liner properties that return a single stored value
- `__all__`, `__init__` files that only re-export names
- Test files (test function names are the documentation)
- Trivial `__init__` that only calls `super().__init__()`

---

## Linter command

```powershell
# Check comment coverage — fails if any function/class is missing a docstring
.venv\Scripts\python.exe scripts/check_comments.py src/rrr

# Run as part of the full quality gate
.venv\Scripts\python.exe scripts/check_comments.py src/rrr && echo "Comments OK"
```

The linter (`scripts/check_comments.py`) checks:
- Every module has a module docstring
- Every non-trivial class has a class docstring
- Every public and private function/method (≥ 3 lines of body) has a docstring
- Reports file + line number for each violation so fixes are easy to locate

---

## When to apply

Apply these standards to **every file you create or modify**. You do not need to
re-comment untouched files in the same PR, but any file you edit must be brought to
standard before the change is merged.
