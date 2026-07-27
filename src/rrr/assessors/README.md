# Assessors

Each assessor is an independent agent that evaluates one release readiness dimension,
produces a deterministic numeric score and a list of risk factors, then asks the LLM
provider to write the evidence narrative.

**21 assessors total:** 7 weighted (contribute to the score) + 14 gate-only (can cap
the verdict via risk factor severity, but weight = 0).

---

## The assessor contract

Every assessor extends `BaseAssessor` and implements two methods:

| Method | Responsibility |
|---|---|
| `_assess()` | All deterministic computation: reads data, runs tools, computes score, extracts risk factors. Returns `DeterministicAssessment`. |
| `_build_reasoning_request()` | Constructs the `ReasoningRequest` sent to the LLM provider for the evidence narrative. |

The base class orchestrates the rest: calling `_assess()`, handing the result to the
provider via `reason()`, computing confidence from tool outcomes (FR-12), and building
the final `DimensionResult`.

**Critical invariant:** `_assess()` must never call `self.provider` or `self.reason()`.
The LLM is invoked only by the base class, after `_assess()` returns.

---

## Severity → verdict gate mapping (ADR-0013)

| Risk factor severity | Verdict cap |
|---|---|
| `CRITICAL` | NO_GO (hard veto) |
| `MAJOR` | CONDITIONAL (soft veto) |
| `MINOR` | No gate effect (informational) |

---

## Weighted assessors

| File | Class | Weight | Source |
|---|---|---|---|
| `test_readiness_assessor.py` | `TestReadinessAssessor` | 0.27 | brain |
| `scope_assessor.py` | `ScopeAssessor` | 0.23 | brain |
| `environment_assessor.py` | `EnvironmentAssessor` | 0.18 | brain + environment.json |
| `dependency_assessor.py` | `DependencyAssessor` | 0.13 | brain + dependency.json |
| `estimation_assessor.py` | `EstimationAssessor` | 0.09 | brain |
| `operability_assessor.py` | `OperabilityAssessor` | 0.07 | operability.json |
| `observability_assessor.py` | `ObservabilityAssessor` | 0.03 (opt-in) | observability.json |

---

## Gate-only assessors

All gate-only assessors have `weight = 0`. They activate by adding the corresponding
source to the `sources:` config block.

| File | Class | Gate trigger |
|---|---|---|
| `rollback_assessor.py` | `RollbackAssessor` | No rollback plan → CONDITIONAL |
| `security_assessor.py` | `SecurityComplianceAssessor` | Critical CVE or SAST failure → NO_GO |
| `performance_assessor.py` | `PerformanceAssessor` | Load test failed / p99 > 2× SLO → NO_GO |
| `accessibility_assessor.py` | `AccessibilityAssessor` | WCAG failures → CONDITIONAL |
| `auditability_assessor.py` | `AuditabilityAssessor` | Incomplete audit log → CONDITIONAL |
| `disaster_recovery_assessor.py` | `DisasterRecoveryAssessor` | No DR plan → NO_GO |
| `data_reconciliation_assessor.py` | `DataReconciliationAssessor` | Integrity check broken → NO_GO |
| `failure_mode_assessor.py` | `FailureModeAssessor` | Undocumented critical failures → CONDITIONAL |
| `dependency_risk_assessor.py` | `DependencyRiskAssessor` | Critical vuln → NO_GO |
| `production_readiness_assessor.py` | `ProductionReadinessAssessor` | Missing migrations/flags → CONDITIONAL |
| `architecture_fitness_assessor.py` | `ArchitectureFitnessAssessor` | Fitness function failures → CONDITIONAL |
| `architecture_drift_assessor.py` | `ArchitectureDriftAssessor` | Code-vs-arch divergence → CONDITIONAL |

---

## Adding a new assessor

1. Create `<name>_assessor.py` extending `BaseAssessor`.
2. Create `src/rrr/models/<name>.py` with an `InputContract` subclass.
3. Add a `<name>SourceReader` in `src/rrr/tools/source_readers.py`.
4. Add a `data/<name>.json` stub.
5. Register in `src/rrr/assessors/__init__.py` and wire into `src/rrr/pipeline.py`.
6. Add `tests/unit/test_<name>_assessor.py` with ≥ 1 golden fixture assertion.
7. Run the full quality gate.

Full pattern: [.claude/rules/assessor-pattern.md](../../../.claude/rules/assessor-pattern.md)
