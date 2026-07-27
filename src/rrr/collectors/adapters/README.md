# Collector Adapters

Automated data-pull adapters for populating dimension JSON files from CI/CD tools
without interactive prompts. Each adapter implements `BaseCollector` and translates a
tool-specific output format into the corresponding `InputContract` model.

---

## Available adapters

### `K6Adapter`

Reads a **k6** `--summary-export` JSON file and maps the performance metrics to
`PerformanceInput` fields.

```python
from rrr.collectors.adapters import K6Adapter

adapter = K6Adapter(summary_path="k6-summary.json")
```

**What it extracts:**
- `http_req_duration` p99 → `p99_latency_ms`
- `http_req_failed` rate → `error_rate`
- `virtual_users_max` → `peak_vus`
- Pass/fail status from threshold outcomes

**k6 run example:**

```bash
k6 run --summary-export k6-summary.json load_test.js
```

---

### `SnykAdapter`

Runs `snyk test --json` as a subprocess and parses the structured JSON output into
`SecurityInput` fields.

```python
from rrr.collectors.adapters import SnykAdapter

adapter = SnykAdapter()
```

**What it extracts:**
- CVE counts by severity (critical / high / medium / low)
- SAST status (pass/fail)
- Dependency vulnerability list

**Requirements:** `SNYK_TOKEN` environment variable must be set (never in config files).

---

### `SonarQubeAdapter`

Queries the **SonarQube** `/api/issues/search` REST API and maps issues to
`SecurityInput` fields.

```python
from rrr.collectors.adapters import SonarQubeAdapter

adapter = SonarQubeAdapter(
    host="http://127.0.0.1:9000",   # must be 127.0.0.1 or localhost (ADR-0010)
    token="${SONAR_TOKEN}",
    project_key="my-project",
)
```

**What it extracts:**
- BLOCKER / CRITICAL issue counts → `critical_cve_count` / `high_cve_count`
- MAJOR / MINOR issue counts → `medium_cve_count` / `low_cve_count`
- Overall quality gate status → `sast_status`

---

## Using adapters with CollectorRunner

```python
from rrr.collectors.base import CollectorConfig
from rrr.collectors.runner import CollectorRunner
from rrr.collectors.adapters import K6Adapter, SnykAdapter, SonarQubeAdapter
from rrr.models.performance import PerformanceInput
from rrr.models.security import SecurityInput

config = CollectorConfig(release="MyRelease RC", data_dir="data")
runner = CollectorRunner()

# Pull performance data from k6 and write to data/performance.json
runner.run("performance", K6Adapter(summary_path="k6.json"), config, PerformanceInput)

# Pull security data from Snyk and write to data/security.json
runner.run("security", SnykAdapter(), config, SecurityInput)
```

---

## Local-only constraint (ADR-0010)

All adapters that make network calls must connect to `127.0.0.1` or `localhost` only in
Phase 1. The SonarQubeAdapter `host` is validated against the `allowed_hosts` config
list at runtime.
