# Models

Pydantic v2 data models that carry typed, validated data across all module boundaries.
No raw dicts are passed between modules — every structure is a typed model.

---

## Two model postures

| Posture | Base class | `extra` config | Use for |
|---|---|---|---|
| **Output / value object** | `RRRModel` | `frozen=True, extra='forbid'` | `DimensionResult`, `AssessmentOutputModel`, LLM I/O — immutable, closed schema |
| **Input contract** | `InputContract` | `extra='ignore'` | Upstream data from brain/env/dep — tolerates extra fields from evolving sources |

---

## Model inventory

| File | Key models | Purpose |
|---|---|---|
| `assessment.py` | `AssessmentOutputModel`, `AuditTrail` | Full assessment result persisted to SQLite and returned by the pipeline |
| `dimension.py` | `DimensionResult`, `DeterministicAssessment` | Per-dimension score, risk factors, evidence, and narrative |
| `evidence.py` | `Evidence`, `ToolInvocation` | Structured tool invocation records attached to a `DimensionResult` |
| `enums.py` | `Verdict`, `DimensionName`, `RiskSeverity`, `TrendDirection`, `ReleaseRiskTier` | All enumerations — single source of truth |
| `risk.py` | `RiskFactor` | A single finding with severity, description, and gate reference |
| `trend.py` | `TrendPoint` | Delta + direction for one dimension between two assessments |
| `llm_io.py` | `ReasoningRequest`, `ReasoningResponse` | LLM provider I/O contract |
| `scope.py` | `ScopeInput` | Brain-derived scope/story-point data |
| `estimation.py` | `EstimationInput` | Brain-derived velocity and earned-value data |
| `test_readiness.py` | `TestReadinessInput` | Brain-derived test pass rates and defect counts |
| `environment.py` | `EnvironmentInput` | Environment provisioning and stability |
| `dependency.py` | `DependencyInput` | Inter-release dependency completion |
| `operability.py` | `OperabilityInput` | Runbooks, deployment checklist |
| `observability.py` | `ObservabilityInput` | Monitoring and alerting coverage |
| `rollback.py` | `RollbackInput` | Rollback plan and test status |
| `security.py` | `SecurityInput`, `SastStatus`, `DastStatus` | SAST/DAST results, CVE counts |
| `performance.py` | `PerformanceInput` | Load test results, p99 latency, SLO |
| `accessibility.py` | `AccessibilityInput` | WCAG compliance |
| `auditability.py` | `AuditabilityInput` | Audit log completeness |
| `disaster_recovery.py` | `DisasterRecoveryInput` | DR plan, RTO/RPO, last test date |
| `data_reconciliation.py` | `DataReconciliationInput` | Data integrity check results |
| `failure_mode.py` | `FailureModeInput` | FMEA documentation status |
| `dependency_risk.py` | `DependencyRiskInput` | External dependency vulnerability posture |
| `production_readiness.py` | `ProductionReadinessInput` | Feature flags, DB migrations, rollout plan |
| `architecture_fitness.py` | `ArchitectureFitnessInput` | Fitness function results |
| `architecture_drift.py` | `ArchitectureDriftInput` | Code-vs-architecture alignment |

---

## Field requirements

Every field must have:
- Explicit type annotation
- `Field(description="...")` — descriptions become LLM prompt context

Cross-field constraints use `@model_validator(mode='after')`.

---

## After any model change

1. Run `mypy src` — all models must be type-clean.
2. If the change affects a field used in golden fixtures, update the fixture and re-run
   the affected golden tests.
3. If the change affects a `DimensionResult` or `AssessmentOutputModel` field, check
   `src/rrr/output/` templates for rendering impact.
