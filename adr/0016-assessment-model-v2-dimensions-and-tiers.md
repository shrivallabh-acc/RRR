# ADR 0016: Assessment Model v2 — New Dimensions, Gate-Only Dimensions, Release Risk Tiers

- **Status:** Accepted (implemented 2026-07-09 — all 16 items complete)
- **Date:** 2026-06-16

## Context
The five Phase-1 dimensions (Scope, Estimation, Environment, Test Readiness, Dependency) have two
gaps the design review surfaced:

1. **They conflate two questions.** Scope (0.25) + Estimation (0.10) = **35% of the score is
   *delivery/estimation performance*** ("was this a well-run program?"), not *ship safety* ("is it
   safe to release now?"). A feature-complete release with no rollback plan can score GO; a
   70%-complete release whose shipped slice is safe can be penalized.
2. **They omit the factors that most often actually block a real release:** operational/deploy &
   rollback readiness, security & compliance, and performance/NFR.

The architecture is extensible (NFR-7), but the **flat weights-sum-to-1.0 model** means each new
*weighted* dimension dilutes the others, and one-size thresholds ignore that a hotfix and a major
launch have different bars.

## Decision (proposed)
1. **Add Operational / Deploy-Rollback** as a new **weighted** dimension — tested rollback, deploy
   runbook, feature flags, monitoring/alerting/on-call, migration reversibility. (Highest real-world
   value; `Environment` today covers *provisioning*, not *deployability/recoverability*.)
2. **Add Security & Compliance** as a **gate-only** dimension — SAST/DAST, open critical CVEs,
   license/data-privacy sign-off. Modeled as a **veto gate** (critical finding → NO_GO) via
   ADR-0013/0014, **with no weight**, so it can't be averaged away.
3. **(Optional) Add Performance / NFR** — load/perf vs SLOs, capacity.
4. **Introduce a dimension class: `weighted` vs `gate-only`.** Gate-only dimensions contribute caps,
   not score — they don't dilute weights.
5. **Release risk tiers** (e.g. `hotfix` / `standard` / `major`) selecting the threshold set and
   required-dimension set per release.
6. **Separate ship-safety from delivery-performance** in how the verdict is framed (e.g. report them
   distinctly, or down-weight Scope/Estimation in the safety verdict).

Each new dimension needs a data contract like the brain/env/dep ones; some sources are Phase-2.

## Consequences
- The verdict reflects the factors release managers actually weigh; security can't be diluted away.
- Gate-only dimensions extend coverage without re-tuning weights.
- Requires new input contracts + data sources (operational/security/perf), some external (Phase 2);
  weights re-tuned when Operational is added; risk-tier config added.

## Alternatives Considered
- **Keep 5 dimensions** — rejected: under-models "readiness"; omits the top blockers.
- **Make every new dimension weighted** — rejected: dilution, and a critical security finding must
  veto, not be averaged into a passing score.
- **One global threshold set** — rejected: ignores release-type risk; hotfix ≠ major launch.

## Implementation notes

**2026-06-22 — Operational / Deploy-Rollback (item 1) built:**
`OperationalAssessor` added (weight 0.10; pipeline_score 60% + rollback_score 40%).
`OperationalInput`, `OperationalSourceReader`, `PipelineStatus`, `RollbackStatus` enums.
Change-freeze and red pipeline raise CRITICAL (→ NO_GO cap). No-rollback-plan raises MAJOR.
Weights rebalanced from 5-dim to 6-dim: test_readiness 0.27, scope 0.23, environment 0.18,
dependency 0.13, estimation 0.09, operational 0.10. Golden fixtures updated; 10 new tests.

**2026-06-29 — Security & Compliance gate-only dimension (item 2) built:**
`SecurityComplianceAssessor` added (weight = 0; gate-only via ADR-0013 risk-factor severity).
`SecurityInput`, `SecuritySourceReader`, `SastStatus`, `DastStatus` enums added.
`SecurityAssessorConfig` (high_cve_threshold = 5) added to `AssessorsConfig`.
`sources.security: DataSource | None` added to `SourcesConfig` — dimension is opt-in: assessor
is wired into the pipeline only when the source is configured. Existing configs are unaffected.
CRITICAL risks: SAST failed, DAST failed, open critical CVEs > 0, data_privacy_approved = False.
MAJOR risks: open_high_cves ≥ threshold, license_approved = False.
MINOR risk: pen_test_passed = None or False (advisory signal, no verdict cap).
`data/security.json` stub added (clean posture). 23 new tests in `test_security_assessor.py`.
Items 3–6 (Performance/NFR, risk tiers, ship-safety split) remain deferred to Phase 2/3.

**2026-07-01 — Performance / NFR gate-only dimension (item 3) built:**
`PerformanceAssessor` added (weight = 0; gate-only via ADR-0013 risk-factor severity).
`PerformanceInput`, `PerformanceSourceReader`, `PerformanceTestStatus` enum added.
`PerformanceAssessorConfig` (low_capacity_threshold_pct = 20.0, slo_critical_multiplier = 2.0)
added to `AssessorsConfig`. `sources.performance: DataSource | None` added to `SourcesConfig` —
dimension is opt-in: assessor is wired into the pipeline only when the source is configured.
Score formula: 0.5×perf_status + 0.3×latency_score + 0.2×capacity_score (informational only).
CRITICAL risks: load test failed; P99 latency ≥ slo_critical_multiplier × SLO threshold.
MAJOR risks: any SLO latency breach; capacity headroom < low_capacity_threshold_pct.
MINOR risk: load test not run (advisory signal, no verdict cap; also reduces confidence to 0.75).
`data/performance.json` stub added (clean posture: passed, 180 ms p99 vs 500 ms SLO, 45% headroom).
25 new tests in `test_performance_assessor.py`. Items 4–6 (risk tiers, ship-safety split) remain.

---

## Decision extension — 2026-07-04 (Assessment Model v2 Extended)

The original 6-item decision is extended with 10 additional items (items 7–16) covering the
OperationalAssessor split and 9 further gate-only assessors. All follow the established
gate-only pattern (weight=0, ADR-0013 severity → verdict cap, opt-in via `sources.<dim>`).

Full input contracts and gathering procedures: `docs/assessor_inputs.md`.
Human and automated collection guide: `docs/data-collection-guide.md`.

**Item 7 — OperationalAssessor split:**
The single `OperationalAssessor` conflates three distinct concerns; split into:
- `OperabilityAssessor` (weighted, 0.07) — deployment pipeline, change management,
  runbooks, on-call, escalation paths. `OperabilityInput`. `data/operability.json`.
- `ObservabilityAssessor` (weighted, 0.03) — dashboards, alerts, SLO monitors, trace
  coverage, log coverage, runbook-to-alert linkage. `ObservabilityInput`. `data/observability.json`.
- `RollbackAssessor` (gate-only) — rollback plan, tested procedure, RTO, data rollback.
  `RollbackInput`. `data/rollback.json`.
Weight rebalance: Operational 0.10 removed; Operability 0.07 + Observability 0.03 added.
Total weighted mass unchanged at 1.00.

**Item 8 — `AccessibilityAssessor` (gate-only):**
WCAG compliance gate. `AccessibilityInput`: wcag_target_level, scan_tool, pages_scanned,
critical_violations, major_violations, minor_violations, manual_review_complete/passed.
CRITICAL: critical_violations > 0. MAJOR: major_violations > 0 or manual review failed.
Tier: excluded for `hotfix`; required for `standard`/`major` on UI-facing releases.

**Item 9 — `AuditabilityAssessor` (gate-only):**
Audit trail completeness gate. `AuditabilityInput`: audit_logging_enabled, regulated_events_logged,
audit_log_immutability_guaranteed, data_retention_days, gdpr_logging_compliant, pii_access_logged,
audit_trail_tested. CRITICAL: logging disabled or PII not logged. MAJOR: GDPR non-compliant or
untested trail.

**Item 10 — `DisasterRecoveryAssessor` (gate-only):**
DR test result gate. `DisasterRecoveryInput`: dr_plan_exists, dr_last_tested_date,
rto_target_minutes, rto_tested_minutes, rpo_target_minutes, rpo_tested_minutes,
failover_tested, data_backup_verified. CRITICAL: plan absent, failover untested, or tested
RTO/RPO exceeds target. MAJOR: backup unverified or stale test (> configured threshold days).

**Item 11 — `DataReconciliationAssessor` (gate-only, opt-in):**
Data migration integrity gate. `DataReconciliationInput`: migration_applicable,
pre/post_migration_record_count, reconciliation_run/date, discrepancy_count/pct,
reconciliation_approved. CRITICAL: reconciliation not run or any discrepancy detected.
MAJOR: reconciliation not approved. Wired only when `sources.data_reconciliation` is configured
AND `migration_applicable=true`.

**Item 12 — `FailureModeAssessor` (gate-only):**
Resilience gate. `FailureModeInput`: failure_modes_documented, critical_paths_covered_pct,
circuit_breakers_configured, timeout_policies_defined, chaos_tests_run, chaos_pass_rate_pct,
chaos_test_date, graceful_degradation_tested, fmea_complete. CRITICAL: failure modes
undocumented, circuit breakers absent. MAJOR: chaos pass rate < threshold or tests not run.

**Item 13 — `DependencyRiskAssessor` (gate-only):**
Third-party supply-chain risk gate. Distinct from `DependencyAssessor` (which tracks internal
programme completion). `DependencyRiskInput`: sca_tool, sca_scan_date, eol_dependencies_count,
critical_transitive_cves, high_transitive_cves, supply_chain_violations,
pinned_dependencies_pct, known_malicious_packages. CRITICAL: malicious packages or critical
transitive CVEs. MAJOR: supply chain violations or high transitive CVEs above threshold.

**Item 14 — `ProductionReadinessAssessor` (gate-only):**
Go-live checklist gate. `ProductionReadinessInput`: capacity_confirmed, feature_flags_configured,
go_live_checklist_complete, stakeholder_sign_offs (product/engineering/security/operations),
release_comms_prepared, support_team_briefed, rollback_decision_criteria_defined,
post_release_monitoring_plan. CRITICAL: capacity unconfirmed or checklist incomplete.
MAJOR: any stakeholder sign-off missing.

**2026-07-09 — Release Risk Tiers + Ship-safety/Delivery-performance split (items 4–6) built:**
`ReleaseRiskTier` enum (`HOTFIX`/`STANDARD`/`MAJOR`) added to `models/enums.py`.
`TierThresholds` and `TiersConfig` Pydantic models added to `config/schema.py`; `for_tier()`
returns the correct `TierThresholds` for the active tier. `tiers:` block added to
`default_config.yaml` (hotfix: go=0.60/no_go=0.30; standard: go=0.80/no_go=0.40;
major: go=0.90/no_go=0.60; each with appropriate `confidence_floor` and `required_gate_dims`).
`--tier` Click option added to CLI. `score_band()` signature changed to accept explicit
`go`/`no_go` floats (allows tier values directly). `triggered_caps()` accepts `excluded_dims`
to suppress gate-only dimension risk factors for the active tier. `derive_verdict()` accepts
`tier_thresholds: TierThresholds | None` — when active, overrides go/no_go/confidence_floor/
required_gate_dims from the tier rather than global thresholds. `split_scores()` added to
`scoring.py` — returns `(ship_safety, delivery_performance)` in [0,1] using the same
weight-redistribution logic. `AssessmentOutputModel` gains three new optional fields:
`tier`, `ship_safety_score`, `delivery_performance_score`. Tier label + sub-scores rendered in
Markdown report and CLI text output. Tier threaded through the full pipeline:
`orchestrator.collect()` → `graph.py` → `pipeline.assess()`/`run_and_record()` → `cli.py`.
29 new tests in `tests/unit/test_tier_thresholds.py`; 2 existing tests updated for the
`score_band()` signature change.

**2026-07-09 — OperationalAssessor split (item 7) built:**
`OperabilityAssessor` (weight 0.07, always-on), `ObservabilityAssessor` (weight 0.03, opt-in),
and `RollbackAssessor` (gate-only weight 0, opt-in) added. `OperationalAssessor` and
`OperationalInput` retained for SQLite backward compatibility but removed from the pipeline.
New models: `OperabilityInput`, `ObservabilityInput`, `RollbackInput` in `src/rrr/models/`.
New readers: `OperabilitySourceReader`, `ObservabilitySourceReader`, `RollbackSourceReader`.
`PipelineStatus` and `RollbackStatus` enums (previously on OperationalInput) remain in
`models/enums.py`. Weights rebalanced: operational 0.10 removed; operability 0.07 + observability
0.03 added; total remains 1.00. Ship-safety dims updated (OPERABILITY + OBSERVABILITY added).
`SourcesConfig`: `operational` → `operability` (required); `observability` and `rollback` added
as opt-in (`DataSource | None`). `configs/osm.yaml` updated. Data stubs: `data/operability.json`,
`data/observability.json`, `data/rollback.json`. Golden fixture inputs added for g1–g5;
`ideal.json` oracles updated for all five fixtures. 66 new tests across
`test_operability_assessor.py`, `test_observability_assessor.py`, `test_rollback_assessor.py`;
orchestration assertions updated in `test_orchestration.py`.

**Item 15 — `ArchitectureFitnessAssessor` (gate-only):**
Automated architecture test gate. `ArchitectureFitnessInput`: tool, scan_date,
fitness_functions_defined, tests_run/passed/failed, coupling_violations, layering_violations,
banned_dependency_violations, violations list. CRITICAL: layering or banned dependency
violations. MAJOR: coupling violations or fitness tests failing.

**Item 16 — `ArchitectureDriftAssessor` (gate-only):**
Architecture baseline compliance gate. `ArchitectureDriftInput`: baseline_version, tool,
assessment_date, adr_compliance_pct, banned_technologies_detected, unapproved_patterns,
tech_standard_violations, drift_score, approved_deviations. CRITICAL: banned technologies
detected or ADR compliance below 80%. MAJOR: unapproved patterns or drift score above threshold.

**2026-07-09 — Items 8–16 (9 gate-only assessors) built:**
`AccessibilityAssessor`, `AuditabilityAssessor`, `DisasterRecoveryAssessor`,
`DataReconciliationAssessor`, `FailureModeAssessor`, `DependencyRiskAssessor`,
`ProductionReadinessAssessor`, `ArchitectureFitnessAssessor`, `ArchitectureDriftAssessor` added.
All follow the gate-only pattern (weight=0, `_assess()` → `DeterministicAssessment`, risk-factor
severity → verdict cap via GateEngine, opt-in via `sources.<dim>` in config). 9 new
`InputContract` models in `src/rrr/models/`; 9 new `_FileApiSourceReader` subclasses in
`src/rrr/tools/source_reader.py`; wired in `src/rrr/pipeline.py`; 9 `DataSource | None` fields
added to `SourcesConfig`; 9 `data/<dim>.json` stubs; 143 new tests across 9 test files.
`DimensionName` enum extended with 9 new entries (ACCESSIBILITY through ARCHITECTURE_DRIFT).
`DataReconciliationAssessor` short-circuits to score=1.0/not_applicable when
`migration_applicable=False`. Total test function count: 676.
