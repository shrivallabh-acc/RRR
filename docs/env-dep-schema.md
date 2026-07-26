# Environment & Dependency Input Contracts

> RRR-owned input contracts implementing **FR-3** (Environment) and **FR-5** (Dependency).
> Unlike the brain contract (upstream RKT — see [brain-schema.md](brain-schema.md)), these are
> defined by RRR. **JSON is canonical**; a CSV form and a localhost-API form carry the *same
> payload* (one schema, three transports). Local-first: any API source must resolve to an
> allow-listed host (`127.0.0.1`/`localhost`, NFR-8 / ADR-0010); source fetch timeout = 10s.

Configured under `sources.environment` / `sources.dependency` in `default_config.yaml`. Format is
inferred from the file extension (`.json` / `.csv`) or `type: api`. Both files optionally carry a
`release` field (the brain `ir_name`) to correlate the snapshot with the release under assessment.
A malformed/absent source fails **only its dimension** and degrades gracefully (ADR-0005).

---

## Environment — `environment.json` (FR-3, ComponentStatusTool)
```json
{
  "schema_version": "1.0.0",
  "release": "Launch 36 - Unified Onboarding",
  "captured_at": "2026-05-28T10:00:00.000Z",
  "components": [
    { "name": "API Gateway",   "provisioning": "validated",   "stability": "stable",   "notes": "" },
    { "name": "Primary DB",     "provisioning": "configured",  "stability": "stable",   "notes": "awaiting validation sign-off" }
  ]
}
```

| `provisioning` | component score | | `stability` | gap severity (risk label) |
|---|---|---|---|---|
| `validated`   | **1.00** | | `down`     | **critical** |
| `configured`  | **0.75** | | `degraded` | **major** |
| `provisioned` | **0.50** | | `stable`   | **minor** |
| `missing`     | **0.00** | | | |

- **Environment score** = `avg(component scores)` (provisioning only).
- **Stability drives risk, not the number.** A `validated` (1.00) component that is `down` still
  scores 1.00 but raises a **critical** risk factor — surfaced in evidence and available to the
  LLM rationale / risk-acceptance. This is intentional per FR-3; the numeric score reflects
  provisioning readiness, severity reflects current operational state.
- **CSV form** (`environment.csv`): header `name,provisioning,stability,notes`, one component/row.

## Dependency — `dependency.json` (FR-5, DependencyTool)
```json
{
  "schema_version": "1.0.0",
  "release": "Launch 36 - Unified Onboarding",
  "captured_at": "2026-05-28T10:00:00.000Z",
  "dependencies": [
    { "name": "Payments Service v2", "completion": "complete",    "integration": "passed",        "owner": "Payments", "notes": "" },
    { "name": "Notification Hub",     "completion": "in_progress", "integration": "not_validated", "owner": "Platform", "notes": "" }
  ]
}
```

- `completion` ∈ `complete | in_progress | not_started`; `integration` ∈ `passed | not_validated | failed`.
- **Dependency score** = `count(completion == complete AND integration == passed) / total`.
- **Classification** (risk label per dependency):
  - **blocking** — `completion == not_started` OR `integration == failed`
  - **at_risk** — `completion == in_progress` AND `integration == not_validated`
  - **on_track** — otherwise
- **CSV form** (`dependency.csv`): header `name,completion,integration,owner,notes`, one dependency/row.

## API transport (optional, local-first)
`sources.environment: { type: api, url: "http://127.0.0.1:PORT/environment" }` — the endpoint
returns the JSON body above. Host must be allow-listed; 10s timeout; on failure, fall back to file
input if configured, else fail the dimension and degrade.

## Validation & degradation
- Validated by Pydantic v2 at ingest (ADR-0004): enum membership, score 0.0–1.0, non-empty
  component/dependency list.
- Empty list or unreadable source → that dimension is unavailable; weight redistributes (ADR-0005);
  verdict stands if ≥ `minimum_assessors` succeed.
