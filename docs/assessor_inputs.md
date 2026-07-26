# Assessor Inputs — Data Gathering Guide

> **Purpose:** Defines what data each RRR assessor needs, where it comes from, how to gather it,
> who is responsible, and when it must be ready. This is the single source of truth for onboarding
> a release into RRR. Fill in the right files at the right time and the pipeline runs fully.
>
> **Scope:** All 19 planned assessors — 3 brain-sourced, 4 supplementary-file (existing, stable),
> 3 from the OperationalAssessor split (Session 2), 9 new gate-only assessors.
>
> **Local-first (ADR-0010):** Every input can be satisfied by a local JSON file in `data/`.
> Phase 2 wires the same `DataSource` config to a live API endpoint — the assessor sees no
> difference. Never add a non-localhost API call without updating the host allow-list.

---

## 1. Source taxonomy

| Type | How it works | Phase |
|------|-------------|-------|
| **Brain JSON** | `rrr-ingest --html-dir input --brain-dir brain` converts the RKT HTML export to `brain/<vs>-history.json`. No extra file needed. | Phase 1 |
| **Local JSON file** | A JSON stub in `data/<dimension>.json`. Can be hand-authored, CI-exported, or tool-generated. Loaded by the dimension's `SourceReader` via `sources.<dim>: {type: file, path: ...}` in the config. | Phase 1 |
| **Localhost API** | `sources.<dim>: {type: api, url: "http://127.0.0.1:PORT/..."}`. Same `SourceReader`; host allow-list enforced at config-load time and per-invocation. | Phase 1 |
| **External API** | `sources.<dim>: {type: api, url: "https://..."}`. Requires the host in the config `allow_list`. Opt-in Phase 2 feature. | Phase 2 |

---

## 2. Assessor registry

All 19 assessors in target-state. `OperationalAssessor` is superseded by the three split assessors
(Session 2 work); until the split lands it remains and covers Operability + Rollback in one.

| # | Assessor | Type | Weight | Source | File | Status |
|---|----------|------|--------|--------|------|--------|
| 1 | ScopeAssessor | Weighted | 0.23 | Brain JSON | `brain/<vs>-history.json` | ✅ Built |
| 2 | EstimationAssessor | Weighted | 0.09 | Brain JSON | `brain/<vs>-history.json` | ✅ Built |
| 3 | TestReadinessAssessor | Weighted | 0.27 | Brain JSON | `brain/<vs>-history.json` | ✅ Built |
| 4 | EnvironmentAssessor | Weighted | 0.18 | File / API | `data/environment.json` | ✅ Built |
| 5 | DependencyAssessor | Weighted | 0.13 | File / API | `data/dependency.json` | ✅ Built |
| 6 | OperabilityAssessor | Weighted | 0.07 | File / API | `data/operability.json` | ✅ Built (2026-07-09) |
| 7 | ObservabilityAssessor | Weighted | 0.03 | File / API | `data/observability.json` | ✅ Built (2026-07-09) |
| 8 | SecurityComplianceAssessor | Gate-only | 0 | File / API | `data/security.json` | ✅ Built |
| 9 | PerformanceAssessor | Gate-only | 0 | File / API | `data/performance.json` | ✅ Built |
| 10 | RollbackAssessor | Gate-only | 0 | File / API | `data/rollback.json` | ✅ Built (2026-07-09) |
| 11 | AccessibilityAssessor | Gate-only | 0 | File / API | `data/accessibility.json` | ⬜ Planned |
| 12 | AuditabilityAssessor | Gate-only | 0 | File / API | `data/auditability.json` | ⬜ Planned |
| 13 | DisasterRecoveryAssessor | Gate-only | 0 | File / API | `data/disaster_recovery.json` | ⬜ Planned |
| 14 | DataReconciliationAssessor | Gate-only | 0 | File / API | `data/data_reconciliation.json` | ⬜ Planned (opt-in) |
| 15 | FailureModeAssessor | Gate-only | 0 | File / API | `data/failure_mode.json` | ⬜ Planned |
| 16 | DependencyRiskAssessor | Gate-only | 0 | File / API | `data/dependency_risk.json` | ⬜ Planned |
| 17 | ProductionReadinessAssessor | Gate-only | 0 | File / API | `data/production_readiness.json` | ⬜ Planned |
| 18 | ArchitectureFitnessAssessor | Gate-only | 0 | File / API | `data/architecture_fitness.json` | ⬜ Planned |
| 19 | ArchitectureDriftAssessor | Gate-only | 0 | File / API | `data/architecture_drift.json` | ⬜ Planned |

> Weight column sums to 1.00 across weighted assessors only. Gate-only assessors have `weight=0`
> and contribute exclusively via CRITICAL/MAJOR risk factor severity → ADR-0013 verdict caps.

---

## 3. Brain-sourced assessors

These three assessors read entirely from `brain/<value-stream>-history.json`.
No supplementary file is needed. The data originates in the RKT Program Metrics HTML export
and is converted by `rrr-ingest`.

### Gathering steps — all three assessors

**Step 1 — Export RKT HTML.**
Download the programme report HTML from the RKT Program Metrics portal.
Save to the `input/` directory (or any folder; pass to `--html-dir`).

**Step 2 — Run `rrr-ingest`.**
```powershell
rrr-ingest --html-dir input --brain-dir brain --value-stream "<value-stream-name>"
```
This produces or updates `brain/<value-stream>-history.json` with an idempotent upsert on snapshot date.

**Step 3 — Verify.**
```powershell
rrr --release "<ir_name>" --list-releases   # lists all known release names
```

**Timing:** Re-ingest whenever the RKT report is refreshed. For release-day go/no-go, use the
most recent export (ideally T-0 or T-1 day).

**Owner:** Release Manager / Programme Delivery team.

---

### 3.1 ScopeAssessor

**Fields consumed from brain JSON:**

| Field | Description |
|-------|-------------|
| `planned_sp` | Total story points planned at sprint start |
| `completed_sp` | Story points closed/delivered |
| `sp_history` | Snapshots of planned SP over time — used for scope-creep detection |

**Risk signals the assessor derives:** +30% scope growth → MAJOR; completion < 50% → CRITICAL.

---

### 3.2 EstimationAssessor

**Fields consumed from brain JSON:**

| Field | Description |
|-------|-------------|
| `planned_value` | Total planned value (PV) at programme start |
| `actual_value` | Earned value (EV) at snapshot date |
| `pv_history` | PV history for trend — `PVPoint(date, planned, actual)` |

**Risk signals:** Variance outside ±10% tolerance → MAJOR; variance outside ±25% → CRITICAL.

---

### 3.3 TestReadinessAssessor

**Fields consumed from brain JSON:**

| Field | Description |
|-------|-------------|
| `sq_avg` | Software quality composite score (0–3 scale; HTML source 0–2, scaled ×1.5) |
| `e2e_passed` | End-to-end tests passed |
| `e2e_planned` | End-to-end tests planned |
| `e2e_run` | End-to-end tests executed |
| `blocker_count` | Open blocker defects |
| `critical_count` | Open critical defects |
| `sq_trend` | Quality trend direction across snapshots |
| `snapshot_date` | Date of the test data — checked against `freshness_max_age_days` (config) |

**Risk signals:** Blockers open → CRITICAL; SQ < 1.0 → MAJOR; stale snapshot → MINOR.

---

## 4. Supplementary-file assessors — existing, stable

These assessors read from a JSON file in `data/` (or a localhost/external API in Phase 2).
Config key: `sources.<dimension>: {type: file, path: "data/<file>.json"}`.

### 4.1 EnvironmentAssessor — `data/environment.json`

**Owner:** Infrastructure / Platform team.
**Timing:** Update before each assessment cycle (T-3 days minimum).
**Phase 1 gathering:** Export from your IaC tooling (Terraform state, Ansible inventory) or
complete manually for each component.

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `components` | list | Each component: `name`, `provisioning_status`, `stability_status` |
| `provisioning_status` | enum | `validated / configured / provisioned / missing` |
| `stability_status` | enum | `stable / degraded / down` |

See `data/environment.json` for the full stub. Existing schema — `EnvironmentInput` in `src/rrr/models/environment.py`.

---

### 4.2 DependencyAssessor — `data/dependency.json`

**Owner:** Programme Delivery / Development team leads.
**Timing:** Updated weekly by programme leads; T-5 days for final read.
**Phase 1 gathering:** Programme leads fill in completion status per dependency.
**Phase 2:** Jira / Azure DevOps API for dependency completion status.

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `dependencies` | list | Each dep: `name`, `completion_pct`, `integration_status`, `blocking` |
| `completion_pct` | float 0–100 | Percentage of dependency work complete |
| `integration_status` | enum | `passed / not_validated / failed` |
| `blocking` | bool | True if this dep blocks release |

See `data/dependency.json` for the full stub. Existing schema — `DependencyInput` in `src/rrr/models/dependency.py`.

---

### 4.3 SecurityComplianceAssessor — `data/security.json`

**Owner:** Security / AppSec team.
**Timing:** Final scan T-1 day; initial scan T-7 days.
**Phase 1 gathering:** Export from SAST tool (SonarQube, Checkmarx, Semgrep) and DAST tool
(OWASP ZAP, Burp) as JSON. Map results to the fields below.
**Phase 2:** API integration with security platform (Snyk, Mend, Veracode).

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `sast_status` | enum | `passed / failed / not_run` |
| `dast_status` | enum | `passed / failed / not_run` |
| `open_critical_cves` | int | Open critical CVEs in the release image |
| `open_high_cves` | int | Open high CVEs |
| `license_approved` | bool\|null | Dependency licence review signed off |
| `data_privacy_approved` | bool\|null | GDPR/data-privacy impact assessment signed off |
| `pen_test_passed` | bool\|null | Penetration test run and passed |

See `data/security.json` for the full stub. Existing schema — `SecurityInput` in `src/rrr/models/security.py`.

**Gate logic:** `sast_status=failed` or `open_critical_cves > 0` or `data_privacy_approved=False` → CRITICAL (NO_GO cap).
`open_high_cves ≥ threshold` or `license_approved=False` → MAJOR (CONDITIONAL cap).

---

### 4.4 PerformanceAssessor — `data/performance.json`

**Owner:** Performance Engineering / SRE team.
**Timing:** Load test T-5 to T-7 days; capacity confirmation T-3 days.
**Phase 1 gathering:** Export load-test results from k6, Gatling, or JMeter as JSON. Map P99 latency.
**Phase 2:** API integration with APM platform (Datadog, New Relic, Grafana).

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `performance_test_status` | enum | `passed / failed / not_run` |
| `p99_latency_ms` | float\|null | Observed P99 response time (ms) |
| `slo_p99_threshold_ms` | float\|null | SLO target for P99 (ms) |
| `capacity_headroom_pct` | float\|null | Available capacity headroom (%) — e.g., 40.0 = 40% spare |

See `data/performance.json` for the full stub. Existing schema — `PerformanceInput` in `src/rrr/models/performance.py`.

**Gate logic:** Load test failed or P99 ≥ 2× SLO → CRITICAL. Any SLO breach or headroom < threshold → MAJOR.

---

## 5. OperationalAssessor split (done 2026-07-09)

The `OperationalAssessor` has been split into three assessors, each with its own input contract
and data stub. `OperationalAssessor` is retained for SQLite backward compatibility but is no
longer wired into the pipeline.

| Target assessor | Concern | Type | Status |
|-----------------|---------|------|--------|
| **OperabilityAssessor** | Day-2 operations readiness | Weighted (0.07) | ✅ Built |
| **ObservabilityAssessor** | Monitoring, alerting, tracing | Weighted (0.03) | ✅ Built |
| **RollbackAssessor** | Rollback plan + tested recovery | Gate-only | ✅ Built |

---

### 5.1 OperabilityAssessor — `data/operability.json`

**Owner:** Release Manager + Engineering team.
**Timing:** Runbook review T-3 days; change approval T-1 day.
**Phase 1 gathering:** Release manager completes after runbook walkthrough and on-call confirmation.
**Phase 2:** ServiceNow / Jira Service Management API for change management status.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "deployment_pipeline": "green",
  "change_freeze": false,
  "recent_deployment_failures": 0,
  "deployment_duration_minutes": 15,
  "runbook_complete": true,
  "runbook_last_tested_days_ago": 14,
  "on_call_schedule_active": true,
  "escalation_paths_defined": true,
  "change_mgmt_approved": true,
  "operational_docs_reviewed": true
}
```

**Gate logic (via CRITICAL/MAJOR risk factors):**
- `change_freeze=true` → CRITICAL (NO_GO cap).
- `deployment_pipeline=red` → CRITICAL.
- `runbook_complete=false` or `on_call_schedule_active=false` → MAJOR.

---

### 5.2 ObservabilityAssessor — `data/observability.json`

**Owner:** Platform / SRE team.
**Timing:** Dashboard and alert audit T-5 days; final check T-1 day.
**Phase 1 gathering:** SRE team exports dashboard/alert inventory from the monitoring platform.
**Phase 2:** API integration with Grafana, Datadog, or New Relic.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "dashboards_configured": true,
  "dashboards_count": 5,
  "slo_defined": true,
  "slo_alerts_configured": true,
  "alert_coverage_pct": 85.0,
  "trace_coverage_pct": 70.0,
  "log_coverage_pct": 90.0,
  "runbooks_linked_to_alerts_pct": 80.0,
  "monitoring_tool": "grafana"
}
```

**Score contribution:** Lower coverage percentages degrade the weighted score; no single gate trigger.
Confidence cap applied when `slo_defined=false` (you cannot assess safety without defined targets).

---

### 5.3 RollbackAssessor — `data/rollback.json`

**Owner:** Release Manager + DevOps / Platform team.
**Timing:** Rollback plan review T-3 days; tested rollback T-7 days (pre-release rehearsal).
**Phase 1 gathering:** Release manager documents rollback procedure and confirms test outcome.
**Phase 2:** Deployment management platform API (Octopus Deploy, Spinnaker, ArgoCD).

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "rollback_plan": "documented",
  "rollback_tested": true,
  "rollback_test_date": "2026-07-01",
  "estimated_rollback_minutes": 15,
  "automated_rollback_available": false,
  "data_rollback_applicable": false,
  "data_rollback_plan_exists": null
}
```

**Gate logic:**
- `rollback_plan=none` → CRITICAL (NO_GO cap).
- `rollback_plan=partial` or `rollback_tested=false` → MAJOR (CONDITIONAL cap).
- `data_rollback_applicable=true` and `data_rollback_plan_exists=false` → CRITICAL.

---

## 6. New gate-only assessors

All nine new gate-only assessors follow the same pattern:
1. A `data/<dimension>.json` stub is committed as a clean-posture baseline.
2. The assessor is opt-in: it only wires into the pipeline when `sources.<dimension>` is configured.
3. If the source is configured but the file is missing, the dimension is UNAVAILABLE (not a crash).
4. Gate logic operates via CRITICAL/MAJOR risk factors → ADR-0013 verdict caps.

---

### 6.1 AccessibilityAssessor — `data/accessibility.json`

**Owner:** QA / Accessibility team.
**Timing:** Automated scan in CI (every build); manual review T-5 days for complex flows.
**Phase 1 gathering:**
  - Run `axe-core`, WAVE, or Lighthouse against the release candidate.
  - Export violation counts by severity. Map to the fields below.
  - CI pipeline can write the JSON as a build artifact.
**Phase 2:** Deque axe DevTools API, Siteimprove API.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "wcag_target_level": "AA",
  "scan_tool": "axe-core",
  "scan_date": "2026-07-03",
  "pages_scanned": 42,
  "critical_violations": 0,
  "major_violations": 2,
  "minor_violations": 15,
  "manual_review_complete": true,
  "manual_review_passed": true
}
```

**Gate logic:**
- `critical_violations > 0` → CRITICAL (NO_GO cap).
- `major_violations > 0` or `manual_review_passed=false` → MAJOR (CONDITIONAL cap).
- `minor_violations > 0` → MINOR (advisory only).

**Tier note:** Typically excluded for `hotfix` tier (small-scope change with no UI surface).
Required for `standard` and `major` tiers on UI-facing releases.

---

### 6.2 AuditabilityAssessor — `data/auditability.json`

**Owner:** Security / Compliance team.
**Timing:** Audit configuration check T-5 days; sign-off T-1 day.
**Phase 1 gathering:** Security team verifies audit log configuration and tests a regulated event
end-to-end. Complete the JSON manually after walkthrough.
**Phase 2:** SIEM platform API (Splunk, Elastic) or audit management system.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "audit_logging_enabled": true,
  "regulated_events_logged": ["login", "logout", "data_export", "config_change"],
  "audit_log_immutability_guaranteed": true,
  "data_retention_days": 365,
  "gdpr_logging_compliant": true,
  "pii_access_logged": true,
  "audit_trail_tested": true,
  "audit_trail_test_date": "2026-07-01"
}
```

**Gate logic:**
- `audit_logging_enabled=false` or `pii_access_logged=false` → CRITICAL.
- `gdpr_logging_compliant=false` or `audit_trail_tested=false` → MAJOR.
- `audit_log_immutability_guaranteed=false` → MAJOR.

---

### 6.3 DisasterRecoveryAssessor — `data/disaster_recovery.json`

**Owner:** Infrastructure / SRE team.
**Timing:** DR test T-30 to T-60 days (quarterly); results remain valid until the next test.
Verify `dr_last_tested_date` is within the configured freshness window.
**Phase 1 gathering:** DR test lead completes after the scheduled failover exercise.
**Phase 2:** DR management platform API or BC/DR tool.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "dr_plan_exists": true,
  "dr_plan_version": "2.3",
  "dr_last_tested_date": "2026-05-15",
  "rto_target_minutes": 60,
  "rto_tested_minutes": 45,
  "rpo_target_minutes": 15,
  "rpo_tested_minutes": 10,
  "failover_tested": true,
  "data_backup_verified": true,
  "cross_region_capable": false
}
```

**Gate logic:**
- `dr_plan_exists=false` or `failover_tested=false` → CRITICAL.
- `rto_tested_minutes > rto_target_minutes` or `rpo_tested_minutes > rpo_target_minutes` → CRITICAL.
- `data_backup_verified=false` → MAJOR.
- `dr_last_tested_date` older than configured staleness threshold → MAJOR.

**Tier note:** Required for `major` tier; optional for `standard`; excluded for `hotfix`.

---

### 6.4 DataReconciliationAssessor — `data/data_reconciliation.json`

**Owner:** Data Engineering team.
**Timing:** Reconciliation report T-1 day (after migration dry-run or shadow migration).
**Phase 1 gathering:** Data Engineering runs the reconciliation script and exports results.
**Phase 2:** Data quality platform API or ETL orchestrator (dbt, Airflow).

> **Opt-in only.** This assessor is only wired when `sources.data_reconciliation` is configured.
> Releases with no data migration should not configure this source.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "migration_applicable": true,
  "pre_migration_record_count": 1500000,
  "post_migration_record_count": 1500000,
  "reconciliation_run": true,
  "reconciliation_run_date": "2026-07-03",
  "discrepancy_count": 0,
  "discrepancy_pct": 0.0,
  "reconciliation_approved": true,
  "approved_by": "data-engineering-lead"
}
```

**Gate logic:**
- `reconciliation_run=false` → CRITICAL (can't release without checking).
- `discrepancy_count > 0` or `discrepancy_pct > 0.0` → CRITICAL.
- `reconciliation_approved=false` → MAJOR.

---

### 6.5 FailureModeAssessor — `data/failure_mode.json`

**Owner:** Engineering + SRE team.
**Timing:** Chaos tests T-7 days; FMEA review T-5 days; circuit-breaker audit T-3 days.
**Phase 1 gathering:** Engineering lead completes after chaos/resilience testing session.
CI/CD pipeline can write chaos test results as a JSON artifact.
**Phase 2:** Chaos engineering platform API (Gremlin, Chaos Monkey, Litmus).

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "failure_modes_documented": true,
  "critical_paths_covered_pct": 90.0,
  "circuit_breakers_configured": true,
  "timeout_policies_defined": true,
  "chaos_tests_run": true,
  "chaos_pass_rate_pct": 95.0,
  "chaos_test_date": "2026-07-01",
  "graceful_degradation_tested": true,
  "fmea_complete": false
}
```

**Gate logic:**
- `failure_modes_documented=false` → CRITICAL.
- `circuit_breakers_configured=false` or `timeout_policies_defined=false` → CRITICAL.
- `chaos_tests_run=true` and `chaos_pass_rate_pct < 80.0` → CRITICAL.
- `chaos_tests_run=false` → MAJOR (advisory: tests not run).
- `fmea_complete=false` → MINOR.

---

### 6.6 DependencyRiskAssessor — `data/dependency_risk.json`

**Owner:** Security / DevSecOps team.
**Timing:** SCA scan in CI (every build); review T-3 days.

> **Distinct from DependencyAssessor** (which tracks internal programme dependency completion).
> `DependencyRiskAssessor` covers third-party supply-chain risk: EOL libraries, transitive CVEs,
> and known malicious packages. Do not conflate the two.

**Phase 1 gathering:** Export from SCA tool (Snyk, Mend, OWASP Dependency-Check, Black Duck).
Most SCA tools produce JSON reports; map to the fields below.
**Phase 2:** SCA tool API (Snyk API, Mend API).

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "sca_tool": "snyk",
  "sca_scan_date": "2026-07-03",
  "eol_dependencies_count": 0,
  "critical_transitive_cves": 0,
  "high_transitive_cves": 2,
  "supply_chain_violations": 0,
  "pinned_dependencies_pct": 95.0,
  "known_malicious_packages": 0
}
```

**Gate logic:**
- `known_malicious_packages > 0` → CRITICAL.
- `critical_transitive_cves > 0` → CRITICAL.
- `eol_dependencies_count > 0` (in critical path) → CRITICAL.
- `supply_chain_violations > 0` or `high_transitive_cves > configured_threshold` → MAJOR.
- `pinned_dependencies_pct < 90.0` → MINOR.

---

### 6.7 ProductionReadinessAssessor — `data/production_readiness.json`

**Owner:** Release Manager (aggregates sign-offs from multiple teams).
**Timing:** Initial checklist T-3 days; all sign-offs required T-0 for `major`/`standard` tiers.
**Phase 1 gathering:** Release manager completes the checklist by collecting confirmations from
each stakeholder (product, engineering, security, operations).
**Phase 2:** Release management platform API (Jira, ServiceNow Change Management).

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "capacity_confirmed": true,
  "feature_flags_configured": true,
  "go_live_checklist_complete": true,
  "stakeholder_sign_offs": {
    "product": true,
    "engineering": true,
    "security": true,
    "operations": true
  },
  "release_comms_prepared": true,
  "support_team_briefed": true,
  "rollback_decision_criteria_defined": true,
  "post_release_monitoring_plan": true
}
```

**Gate logic:**
- `capacity_confirmed=false` → CRITICAL.
- `go_live_checklist_complete=false` → CRITICAL.
- Any `stakeholder_sign_offs` value `false` → MAJOR (each missing sign-off is a separate MAJOR risk).
- `support_team_briefed=false` or `rollback_decision_criteria_defined=false` → MAJOR.
- `release_comms_prepared=false` or `post_release_monitoring_plan=false` → MINOR.

---

### 6.8 ArchitectureFitnessAssessor — `data/architecture_fitness.json`

**Owner:** Architecture team (automated in CI/CD pipeline).
**Timing:** Fitness functions run as part of every build; export JSON result as a build artifact.
Final review T-5 days.
**Phase 1 gathering:** Fitness functions run in CI (ArchUnit for Java, `import-linter` for Python,
custom scripts). The pipeline writes the JSON report. Map results to the fields below.
**Phase 2:** Architecture governance platform API or CI/CD pipeline artifact API.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "tool": "import-linter",
  "scan_date": "2026-07-03",
  "fitness_functions_defined": 12,
  "tests_run": 12,
  "tests_passed": 12,
  "tests_failed": 0,
  "coupling_violations": 0,
  "layering_violations": 0,
  "banned_dependency_violations": 0,
  "violations": []
}
```

Each entry in `violations`:
```json
{ "rule": "no-cross-domain-import", "file": "src/x/y.py", "severity": "critical" }
```

**Gate logic:**
- `layering_violations > 0` or `banned_dependency_violations > 0` → CRITICAL.
- `coupling_violations > 0` or `tests_failed > 0` → MAJOR.
- `fitness_functions_defined == 0` → MAJOR (no governance in place).

---

### 6.9 ArchitectureDriftAssessor — `data/architecture_drift.json`

**Owner:** Architecture team.
**Timing:** Drift assessment T-7 days (before release branch cut); T-0 for `major` tier.
**Phase 1 gathering:** Architecture team runs drift analysis comparing the current codebase against
the approved architecture baseline. Tools: `pyreverse`, `dependency-cruiser`, custom ADR-compliance
scripts. Export results as JSON.
**Phase 2:** Architecture governance platform API or static analysis tool API.

```json
{
  "schema_version": "1.0.0",
  "release": "<ir_name>",
  "captured_at": "2026-07-04T09:00:00.000Z",
  "baseline_version": "v2.0.0",
  "tool": "dependency-cruiser",
  "assessment_date": "2026-07-03",
  "adr_compliance_pct": 95.0,
  "banned_technologies_detected": [],
  "unapproved_patterns": [],
  "tech_standard_violations": [],
  "drift_score": 0.05,
  "approved_deviations": ["temporal-coupling-service-a"]
}
```

**Gate logic:**
- `banned_technologies_detected` non-empty → CRITICAL.
- `adr_compliance_pct < 80.0` → CRITICAL.
- `unapproved_patterns` non-empty or `tech_standard_violations` non-empty → MAJOR.
- `drift_score > configured_threshold` (e.g., 0.20) → MAJOR.
- `drift_score > minor_threshold` (e.g., 0.10) → MINOR.

---

## 7. Gathering timeline

When each data file must be ready relative to release day (T-0).

| Window | Assessors / Actions |
|--------|-------------------|
| **T-10 days** | Architecture Fitness (automated CI), Architecture Drift, Dependency Risk (SCA scan) |
| **T-7 days** | Performance (load test run), Disaster Recovery (if not done quarterly), Failure Mode (chaos tests) |
| **T-5 days** | Accessibility (scan + manual review start), Observability (dashboard/alert audit), Architecture Fitness final review |
| **T-3 days** | Environment (infra check), Operability (runbook review + on-call confirm), Rollback (plan review), Auditability (audit log check), Failure Mode (FMEA review), Production Readiness (initial checklist) |
| **T-1 day** | Security (final scan), Dependency (final status update), Auditability (sign-off), Data Reconciliation (after dry-run), Production Readiness (all sign-offs for `major`) |
| **T-0 (release day)** | Brain data (fresh RKT ingest), Production Readiness (final confirmation), final `rrr --release "..." --tier <tier>` verdict run |

---

## 8. Responsibility map

| Assessor | Primary owner | Supporting team |
|----------|--------------|----------------|
| Scope, Estimation, Test Readiness | Release Manager | Programme Delivery |
| Environment | Infrastructure / Platform | DevOps |
| Dependency (internal) | Programme Lead | Engineering team |
| Operability | Release Manager | Engineering + Operations |
| Observability | SRE / Platform | DevOps |
| Rollback | Release Manager | DevOps / Platform |
| Security & Compliance | Security / AppSec | DevSecOps |
| Performance | Performance Engineering | SRE |
| Accessibility | QA Lead | Engineering (frontend) |
| Auditability | Compliance / Security | Engineering |
| Disaster Recovery | Infrastructure / SRE | Operations |
| Data Reconciliation | Data Engineering | Programme Delivery |
| Failure Mode | Engineering Lead | SRE |
| Dependency Risk (third-party) | Security / DevSecOps | Engineering |
| Production Readiness | Release Manager | All stakeholders |
| Architecture Fitness | Architecture team | CI/CD pipeline |
| Architecture Drift | Architecture team | Engineering |

---

## 9. Tier requirement matrix

Which assessors are **required**, **optional**, or **excluded** per release risk tier.
"Required" means: if the assessor is configured but returns UNAVAILABLE, verdict → INCOMPLETE.
"Excluded" means: assessor skipped even if source is configured.
"Optional" means: runs if configured; UNAVAILABLE is tolerated (graceful degradation).

| Assessor | `hotfix` | `standard` | `major` |
|----------|----------|------------|---------|
| Scope | Required | Required | Required |
| Estimation | Optional | Required | Required |
| Test Readiness | Required | Required | Required |
| Environment | Required | Required | Required |
| Dependency (internal) | Optional | Required | Required |
| Operability | Optional | Required | Required |
| Observability | Optional | Required | Required |
| Security & Compliance | Required | Required | Required |
| Performance | Optional | Required | Required |
| Rollback | Required | Required | Required |
| Accessibility | Excluded | Required (UI only) | Required |
| Auditability | Excluded | Optional | Required |
| Disaster Recovery | Excluded | Optional | Required |
| Data Reconciliation | Excluded | Optional (if migration) | Required (if migration) |
| Failure Mode | Excluded | Optional | Required |
| Dependency Risk | Optional | Required | Required |
| Production Readiness | Optional | Required | Required |
| Architecture Fitness | Excluded | Optional | Required |
| Architecture Drift | Excluded | Optional | Required |

> `Required (UI only)` — Accessibility is required for standard/major releases that include a UI
> surface. Releases with no UI changes may configure it as Optional at the programme level.
> `Required (if migration)` — DataReconciliation is required whenever `migration_applicable=true`.

---

## 10. Config wiring reference

Each supplementary assessor is opt-in: it only activates when the corresponding `sources.<key>`
is present in the config file. Brain-sourced assessors (1–3) always run.

```yaml
sources:
  brain:
    type: file
    path: "brain/<value-stream>-history.json"

  # Existing supplementary sources
  environment:
    type: file
    path: "data/environment.json"
  dependency:
    type: file
    path: "data/dependency.json"
  security:
    type: file
    path: "data/security.json"
  performance:
    type: file
    path: "data/performance.json"

  # Session 2: OperationalAssessor split
  operability:
    type: file
    path: "data/operability.json"
  observability:
    type: file
    path: "data/observability.json"
  rollback:
    type: file
    path: "data/rollback.json"

  # New gate-only assessors (add as data files become available)
  accessibility:
    type: file
    path: "data/accessibility.json"
  auditability:
    type: file
    path: "data/auditability.json"
  disaster_recovery:
    type: file
    path: "data/disaster_recovery.json"
  data_reconciliation:          # opt-in: only for releases with data migrations
    type: file
    path: "data/data_reconciliation.json"
  failure_mode:
    type: file
    path: "data/failure_mode.json"
  dependency_risk:
    type: file
    path: "data/dependency_risk.json"
  production_readiness:
    type: file
    path: "data/production_readiness.json"
  architecture_fitness:
    type: file
    path: "data/architecture_fitness.json"
  architecture_drift:
    type: file
    path: "data/architecture_drift.json"
```

To switch any source to a Phase 2 API:
```yaml
  security:
    type: api
    url: "https://api.snyk.io/v1/projects/<id>/issues"
    # host must be in the config allow_list
```
