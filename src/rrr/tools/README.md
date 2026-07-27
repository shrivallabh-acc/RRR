# Tools

The tool layer provides a uniform invocation interface for all data-reading operations
within assessors. Every tool call is timed out, retried on transient failure, and
recorded in the audit trail (FR-12).

---

## Module overview

| File | Purpose |
|---|---|
| `base.py` | `BaseTool` protocol — the interface every tool must implement |
| `runner.py` | `ToolRunner` — timeout enforcement, retry, and `ToolInvocation` recording |
| `rkt_brain_reader.py` | `RKTBrainReader` — reads brain/*.json and returns typed release data |
| `source_readers.py` | 17 `SourceReader` classes — one per dimension data file |

---

## BaseTool protocol

```python
class BaseTool(Protocol):
    name: str
    def run(self, *args: Any, **kwargs: Any) -> Any: ...
```

Any callable class with a `name` attribute and a `run()` method satisfies the protocol.

---

## ToolRunner

Wraps every tool call with:
- **Timeout** — enforced via `concurrent.futures` with the `assessor_default` or
  `tool_default` timeout from config.
- **Retry** — on `ToolInvocationError`, retries up to `tools.retry_count` times with
  `tools.retry_backoff_s` seconds between attempts.
- **Recording** — each invocation is appended to the assessor's `tool_invocations` list
  as a `ToolInvocation` (tool name, duration, success/failure, truncated output).

```python
result = self.invoke_tool(my_tool, arg1, arg2)   # always via invoke_tool, never directly
```

---

## RKTBrainReader

Reads the brain history JSON and returns strongly-typed release data for the assessors
that use brain data (Scope, Estimation, TestReadiness, Environment, Dependency).

Key methods:
- `read_release(release: str, snapshot: str)` → release record for a given IR name
- `list_releases(snapshot: str)` → all release names in the snapshot
- `list_toc_value_streams()` → distinct TOC value stream tags across all snapshots

---

## Source readers

One `SourceReader` per dimension — reads the dimension JSON file (or API response) and
validates it against the corresponding `InputContract` model.

| Reader | Dimension | Input model |
|---|---|---|
| `EnvironmentSourceReader` | environment | `EnvironmentInput` |
| `DependencySourceReader` | dependency | `DependencyInput` |
| `OperabilitySourceReader` | operability | `OperabilityInput` |
| `ObservabilitySourceReader` | observability | `ObservabilityInput` |
| `RollbackSourceReader` | rollback | `RollbackInput` |
| `SecuritySourceReader` | security | `SecurityInput` |
| `PerformanceSourceReader` | performance | `PerformanceInput` |
| `AccessibilitySourceReader` | accessibility | `AccessibilityInput` |
| `AuditabilitySourceReader` | auditability | `AuditabilityInput` |
| `DisasterRecoverySourceReader` | disaster_recovery | `DisasterRecoveryInput` |
| `DataReconciliationSourceReader` | data_reconciliation | `DataReconciliationInput` |
| `FailureModeSourceReader` | failure_mode | `FailureModeInput` |
| `DependencyRiskSourceReader` | dependency_risk | `DependencyRiskInput` |
| `ProductionReadinessSourceReader` | production_readiness | `ProductionReadinessInput` |
| `ArchitectureFitnessSourceReader` | architecture_fitness | `ArchitectureFitnessInput` |
| `ArchitectureDriftSourceReader` | architecture_drift | `ArchitectureDriftInput` |

---

## Adding a new tool

1. Implement `BaseTool` protocol in a new file.
2. Add it to `__init__.py`.
3. Call it only via `self.invoke_tool()` from within `_assess()` in an assessor.
4. Add tests in `tests/unit/test_tools.py` covering: success path, timeout path, and
   that the `ToolInvocation` record is present in `DimensionResult.evidence`.
