# Collectors

The collector system populates the dimension JSON files in `data/` for the 14
supplementary dimensions that are not derived from brain (RKT) data. Release managers
answer prompts or tool adapters pull data from CI/CD systems.

---

## Module overview

| Module | Purpose |
|---|---|
| `base.py` | `BaseCollector` ABC + `CollectorConfig` data class |
| `runner.py` | `CollectorRunner` — validates, writes, and tracks status |
| `registry.py` | `CollectorRegistry` — 14 registered dimension collectors |
| `interactive.py` | `InteractiveCollector` — derives Click prompts from `InputContract` Pydantic schema |
| `_cli.py` | `rrr-collect` Click entry point |
| `adapters/` | `K6Adapter`, `SnykAdapter`, `SonarQubeAdapter` — automated data pull |

---

## How collection works

1. `CollectorRegistry` maps dimension name → `BaseCollector` subclass.
2. `rrr-collect --all` iterates the registry for the given tier, calling each collector.
3. `InteractiveCollector` reads the `InputContract` Pydantic model for the dimension,
   introspects the field types, and generates appropriate Click prompts:
   - `Enum` field → `click.Choice`
   - `bool` field → `click.confirm`
   - `int`/`float` field → `click.prompt` with numeric type
   - `str` field → `click.prompt` with text type
4. Collected data is validated against the `InputContract` schema.
5. `CollectorRunner.run()` writes the validated JSON to `data/<dimension>.json` and
   stamps it with the collection timestamp.
6. `CollectorRunner.status()` reads existing files and classifies each as FRESH (< 24h),
   STALE (≥ 24h), or MISSING.

---

## The 14 registered dimensions

| Dimension key | `InputContract` model | Data file |
|---|---|---|
| `operability` | `OperabilityInput` | `data/operability.json` |
| `observability` | `ObservabilityInput` | `data/observability.json` |
| `rollback` | `RollbackInput` | `data/rollback.json` |
| `security` | `SecurityInput` | `data/security.json` |
| `performance` | `PerformanceInput` | `data/performance.json` |
| `accessibility` | `AccessibilityInput` | `data/accessibility.json` |
| `auditability` | `AuditabilityInput` | `data/auditability.json` |
| `disaster_recovery` | `DisasterRecoveryInput` | `data/disaster_recovery.json` |
| `data_reconciliation` | `DataReconciliationInput` | `data/data_reconciliation.json` |
| `failure_mode` | `FailureModeInput` | `data/failure_mode.json` |
| `dependency_risk` | `DependencyRiskInput` | `data/dependency_risk.json` |
| `production_readiness` | `ProductionReadinessInput` | `data/production_readiness.json` |
| `architecture_fitness` | `ArchitectureFitnessInput` | `data/architecture_fitness.json` |
| `architecture_drift` | `ArchitectureDriftInput` | `data/architecture_drift.json` |

Brain-backed dimensions (`scope`, `estimation`, `test_readiness`, `dependency`,
`environment`) are not in the collector registry — they come from `rrr-ingest`.

---

## `rrr-collect` CLI

```
rrr-collect --status                             # FRESH/STALE/MISSING per dim
rrr-collect --release "MyRelease" --all          # collect all dims interactively
rrr-collect --release "MyRelease" -d security    # collect one dim
rrr-collect --release "MyRelease" --all --tier hotfix   # skip non-critical dims
rrr-collect --release "MyRelease" -d operability --refresh  # overwrite FRESH file
```

---

## Programmatic use

```python
from rrr.collectors.adapters import K6Adapter
from rrr.collectors.base import CollectorConfig
from rrr.collectors.runner import CollectorRunner
from rrr.models.performance import PerformanceInput

config = CollectorConfig(release="MyRelease", data_dir="data")
adapter = K6Adapter(summary_path="k6-summary.json")
runner = CollectorRunner()
runner.run("performance", adapter, config, PerformanceInput)
```

See [adapters/README.md](adapters/README.md) for adapter-specific details.
