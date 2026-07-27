# data/

Dimension JSON files and local persistence for RRR.

---

## Directory structure

```
data/
  local/
    rrr.sqlite              ← SQLite assessment history (auto-created on first run)
    chroma/                 ← Chroma vector index (only if memory.chroma_path is set)

  environment.json          ← required: environment provisioning and stability
  dependency.json           ← required: inter-release dependency completion
  operability.json          ← required: operational readiness

  observability.json        ← opt-in: monitoring and alerting coverage
  rollback.json             ← opt-in: rollback plan and test status
  security.json             ← opt-in: SAST/DAST results, CVE counts
  performance.json          ← opt-in: load test results, p99 latency
  accessibility.json        ← opt-in: WCAG audit results
  auditability.json         ← opt-in: audit log completeness
  disaster_recovery.json    ← opt-in: DR plan, RTO/RPO, last test date
  data_reconciliation.json  ← opt-in: data integrity check results
  failure_mode.json         ← opt-in: FMEA documentation status
  dependency_risk.json      ← opt-in: external dependency vulnerability posture
  production_readiness.json ← opt-in: feature flags, DB migrations, rollout plan
  architecture_fitness.json ← opt-in: fitness function results
  architecture_drift.json   ← opt-in: code-vs-architecture alignment
```

---

## Populating dimension files

Use `rrr-collect` to populate files interactively:

```powershell
# Check what's fresh, stale, or missing
rrr-collect --status

# Collect all dimensions for a release
rrr-collect --release "RetirePlus RC" --all

# Collect one dimension
rrr-collect --release "RetirePlus RC" --dimension security

# Overwrite a stale file
rrr-collect --release "RetirePlus RC" --dimension environment --refresh
```

Or write them directly — each file is a JSON object matching the corresponding
`InputContract` Pydantic model in `src/rrr/models/`.

---

## File format

Every dimension file is a flat JSON object with typed fields. Example (`security.json`):

```json
{
  "sast_status": "PASSED",
  "dast_status": "PASSED",
  "critical_cve_count": 0,
  "high_cve_count": 2,
  "medium_cve_count": 8,
  "low_cve_count": 15,
  "licence_approvals_complete": true,
  "collected_at": "2026-07-26T09:00:00.000Z",
  "release": "RetirePlus RC/RCP Enrollment"
}
```

---

## Activating optional dimensions

Edit your config YAML to add the source:

```yaml
sources:
  security: { type: file, path: "./data/security.json" }
  performance: { type: file, path: "./data/performance.json" }
```

Then run `rrr-collect --status` to confirm the file exists and is FRESH before assessing.

---

## SQLite database

`data/local/rrr.sqlite` is auto-created on the first `rrr` run. It stores:
- Full `AssessmentOutputModel` JSON per run (compressed)
- Release name, value stream, verdict, score, and timestamp as indexed columns

Back it up before destructive operations. It is the source of truth for the
`rrr-ui` dashboard history and trends panels.
