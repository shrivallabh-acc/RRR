# Config

The configuration system loads a layered YAML config and validates it against a strict
Pydantic v2 schema. Bundled defaults are deep-merged with any user-supplied overrides so
you only need to specify what changes.

---

## Module overview

| File | Purpose |
|---|---|
| `loader.py` | `ConfigLoader.load(path?, overrides?)` — deep-merge + env-var substitution + Pydantic validation |
| `schema.py` | `RRRConfig` root model + all nested config models |
| `default_config.yaml` | Bundled production defaults (always loaded first) |

---

## Loading order

```
default_config.yaml             ← bundled defaults
  ↓ deep-merged with
user config (--config path)     ← optional, only keys you want to override
  ↓ deep-merged with
overrides dict                  ← programmatic overrides (tests, pipeline.py)
  ↓
${VAR_NAME} env-var substitution
  ↓
Pydantic v2 validation → RRRConfig
```

---

## Environment-variable interpolation

Any string value in YAML can use `${VAR_NAME}` syntax:

```yaml
memory:
  sqlite_path: "${DATA_DIR}/rrr.sqlite"
provider:
  claude:
    model: "${CLAUDE_MODEL}"
```

Missing variables raise `ConfigurationError` before validation.

---

## Config schema sections

| Section | Key model | Description |
|---|---|---|
| `weights` | `WeightsConfig` | Per-dimension weights (must sum to 1.0) |
| `thresholds` | `ThresholdsConfig` | GO/NO_GO bands, minimum_assessors, confidence_floor |
| `trend` | `TrendConfig` | improving_delta / degrading_delta (default ±0.05) |
| `gates` | `GatesConfig` | Per-condition gate rules (e2e_critical_floor, blocker_defects, etc.) |
| `timeouts` | `TimeoutsConfig` | Per-assessor and per-tool wall-clock limits in seconds |
| `persistence` | `PersistenceConfig` | SQLite retry attempts and interval |
| `tools` | `ToolsConfig` | Tool invocation retry count and backoff |
| `provider` | `ProviderConfig` | LLM provider type + per-provider blocks |
| `sources` | `SourcesConfig` | Brain dir + 16 dimension source entries |
| `assessors` | `AssessorsConfig` | Per-assessor knobs (thresholds, sub-weights) |
| `tiers` | `TiersConfig` | hotfix / standard / major threshold sets |
| `memory` | `MemoryConfig` | SQLite path + optional Chroma path |
| `ui` | `UiConfig` | HTTP Basic Auth (auth_user, auth_password) |

---

## Programmatic use

```python
from rrr.config import ConfigLoader

# Load defaults only
cfg = ConfigLoader.load()

# Load with a config file
cfg = ConfigLoader.load(path="configs/osm.yaml")

# Load with programmatic overrides (deep-merged last, highest priority)
cfg = ConfigLoader.load(overrides={
    "sources": {"brain": {"dir": "/tmp/brain", "value_stream": "OSM"}},
    "memory": {"sqlite_path": "/tmp/test.sqlite"},
})

# Access typed fields
print(cfg.weights.test_readiness)   # 0.27
print(cfg.thresholds.go)            # 0.80
print(cfg.provider.type)            # "rule_based"
```

---

## Reference configs in `configs/`

| File | Purpose |
|---|---|
| `demo.yaml` | MockLLMProvider + demo brain path — run without real data |
| `osm.yaml` | OSM value stream production settings |
| `claude.yaml` | ClaudeProvider (`claude-sonnet-4-6`) + recommended thresholds |
| `bedrock.yaml` | BedrockProvider + AWS Bedrock model ID |
