# RRR — Release Readiness Results: Comprehensive Architectural Review

> **Reviewer:** Senior AI Enterprise Architect  
> **Date:** 2026-07-09  
> **Version reviewed:** Phase 1 complete · Phase 2 underway · M6 in progress  
> **Scope:** Full codebase · standards compliance · Well-Architected Framework · client asset positioning

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Value Architecture — What This Delivers When Fully Built](#2-value-architecture)
3. [Integration Landscape — Inputs and Integrations Required](#3-integration-landscape)
4. [Client Asset Positioning — Accenture Scale-Out Strategy](#4-client-asset-positioning)
5. [Plug-and-Play Architecture Assessment](#5-plug-and-play-architecture)
6. [Deep Component Analysis](#6-deep-component-analysis)
   - 6.1 [Ingest Layer](#61-ingest-layer-srcrrrringest)
   - 6.2 [Brain Contract & Data Models](#62-brain-contract--data-models-srcrrrmodels)
   - 6.3 [Configuration Layer](#63-configuration-layer-srcrrrconfig)
   - 6.4 [Tools Layer](#64-tools-layer-srcrrrtools)
   - 6.5 [Assessors](#65-assessors-srcrrrrassessors)
   - 6.6 [Orchestration Engine](#66-orchestration-engine-srcrrrrorchestration)
   - 6.7 [Provider Abstraction](#67-provider-abstraction-srcrrrproviders)
   - 6.8 [Memory & Persistence](#68-memory--persistence-srcrrrrmemory)
   - 6.9 [Collectors (Planned)](#69-collectors-planned-srcrrrrcollectors)
   - 6.10 [Web UI Dashboard](#610-web-ui-dashboard-srcrrrui)
   - 6.11 [Pipeline & CLI Composition Root](#611-pipeline--cli-composition-root)
   - 6.12 [Output Layer](#612-output-layer)
   - 6.13 [Test Architecture](#613-test-architecture)
7. [Well-Architected Framework Review](#7-well-architected-framework-review)
   - 7.1 [Operational Excellence](#71-operational-excellence)
   - 7.2 [Security](#72-security)
   - 7.3 [Reliability](#73-reliability)
   - 7.4 [Performance Efficiency](#74-performance-efficiency)
   - 7.5 [Cost Optimization](#75-cost-optimization)
   - 7.6 [Sustainability](#76-sustainability)
8. [Architectural Strengths](#8-architectural-strengths)
9. [Architectural Gaps and Risks](#9-architectural-gaps-and-risks)
10. [Strategic Recommendations](#10-strategic-recommendations)
11. [Achievability Assessment](#11-achievability-assessment)
12. [Appendix: ADR Maturity Scorecard](#12-appendix-adr-maturity-scorecard)

---

## 1. Executive Summary

**RRR (Release Readiness Results)** is a well-conceived, architecturally disciplined Python system that addresses a genuine and recurrent pain point in large-scale delivery organisations: the absence of an objective, auditable, consistent mechanism for deciding whether a software release is safe to ship.

In its current Phase 1 / M6-in-progress state, RRR demonstrates a level of architectural thinking that is uncommon for a system at this maturity level. The deterministic-first invariant, the Pydantic-validated data contract boundary, the LLM-as-narrative-only discipline, and the multi-layer graceful degradation model are all professionally sound choices that would survive an Enterprise Architecture governance review.

**Overall verdict on the project itself: CONDITIONAL GO.**

The core scoring engine, the anti-corruption boundary, the assessor pattern, and the test harness are production-grade. The gaps are in the areas of multi-tenancy, API-first integration, observability instrumentation, and the incomplete collector layer — all of which are acknowledged in the roadmap. This review confirms those gaps are real and proposes a concrete path to address them.

**For Accenture client asset positioning:** The architecture is close to asset-ready but requires three deliberate additions — a tenant isolation model, a deployment packaging model (Helm/Docker Compose), and a data-integration playbook per source system — before it can be proposed as a repeatable delivery accelerator. These are achievable within one additional milestone.

---

## 2. Value Architecture

### 2.1 The Problem This Solves

Release readiness decisions in large programmes are today made through:
- Manual meetings with slide-based status summaries
- Personal judgement by release managers who hold context informally
- Disconnected tooling (JIRA for scope, SonarQube for quality, Dynatrace for ops — no unified signal)
- No audit trail of why a GO/NO-GO decision was made

The consequence: preventable production incidents caused by releases that cleared manual gates but failed objective criteria; and excessive caution that delays releases that were genuinely ready.

### 2.2 Value Delivered When Fully Built

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FULLY BUILT VALUE CHAIN                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SOURCE SYSTEMS          INGEST/COLLECT         ASSESSMENT ENGINE           │
│  ──────────────          ──────────────         ─────────────────           │
│  RKT / JIRA              HTMLExtractor          ScopeAssessor               │
│  SonarQube    ─────────► BrainWriter   ───────► TestReadinessAssessor       │
│  Jenkins/GH   ─────────► SourceReaders ───────► EnvironmentAssessor        │
│  Dynatrace              (planned:               DependencyAssessor          │
│  ServiceNow              rrr-collect)           SecurityAssessor            │
│  Checkmarx                                      PerformanceAssessor         │
│  Veracode                                       (+ 9 gate-only planned)     │
│                                                        │                    │
│                                                        ▼                    │
│  VERDICT ENGINE                      OUTPUT LAYER                           │
│  ──────────────                      ────────────                           │
│  Weighted scoring                    GO / NO-GO / CONDITIONAL               │
│  Gate/veto caps                      Narrative rationale (LLM)              │
│  Tier thresholds ─────────────────►  Remediation plan                      │
│  Confidence floor                    Audit trail                            │
│  Trend analysis                      Markdown / JSON / HTML reports         │
│                                      NiceGUI dashboard                      │
│                                      SQLite history                         │
│                                             │                               │
│                                             ▼                               │
│  DOWNSTREAM CONSUMERS                                                       │
│  ────────────────────                                                       │
│  Release Managers        → One-screen GO/NO-GO with evidence                │
│  Programme Directors     → Trends, portfolio risk posture                   │
│  Engineering Teams       → Per-dimension score + remediation steps          │
│  Audit / Compliance      → Full assessment JSON with evidence chain         │
│  CAB / Change Advisory   → Structured decision record                       │
│  Executives              → Portfolio health KPIs                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Quantified Value Indicators

| Metric | Current (manual) | Target (with RRR) |
|--------|-----------------|-------------------|
| Time to produce release readiness report | 2–4 hours per release | < 2 minutes (automated) |
| Consistency of criteria | Varies by release manager | 100% deterministic (same weights, same gates) |
| Audit trail retention | Slide decks (lost after meeting) | Permanent SQLite + JSON record |
| Coverage of releases per programme | Typically top 5-10 per quarter | All releases, every snapshot |
| Mean time to identify a blocking risk | Post-release (incident) | Pre-release (gate trigger) |
| LLM reasoning auditability | Not applicable | Bounded to narrative only; numeric score is fully reproducible without AI |

### 2.4 The Differentiating Principle

The most important commercial differentiator of this system is the **deterministic-first invariant** (ADR-0006, ADR-0017). Unlike most AI-assisted release tools, the verdict label (`GO` / `NO-GO`) is **never influenced by the LLM output**. This means:
- The decision can be **explained to a regulator** without referencing AI
- The audit trail is **reproducible** — given the same inputs, the same verdict always results
- The LLM failure mode is **narrative degradation, not verdict corruption**
- The system passes ISO 27001 and SOX audit requirements that prohibit AI black-box decisions

This is a genuine competitive differentiator and should be prominent in all client communications.

---

## 3. Integration Landscape

### 3.1 Current Integration State

```
CURRENTLY INTEGRATED:
─────────────────────
RKT Program Metrics HTML export → rrr-ingest → brain/*.json
Local JSON files (environment.json, dependency.json, operational.json)
Local API sources (localhost-only, allow-listed hosts)
Ollama (local LLM, 127.0.0.1)
SQLite (local persistence)
Chroma (local vector store, optional)
Amazon Bedrock (Phase 2, SDK-only)
Anthropic Claude API (Phase 2, SDK-only)
NiceGUI web server (local, 127.0.0.1:8080)
```

### 3.2 Integration Architecture — What Is Required for Enterprise Deployment

The following table maps each assessor dimension to its source system integrations. This is the full integration landscape required for the system to operate fully.

#### Tier 1: Weighted Dimensions (score-bearing)

| Dimension | Source System | Integration Type | Data Collected |
|-----------|--------------|-----------------|----------------|
| **Scope** (0.27 weight post-split) | JIRA / Azure DevOps / RKT | HTML extract or REST API | Story points planned/closed, sprint velocity |
| **Estimation** (0.09) | JIRA / MS Project / RKT | Same as scope | Planned vs actual effort, PV curves |
| **Test Readiness** (0.27) | SonarQube, JIRA, Jenkins, RKT | REST API | Code quality gates, defect counts by severity, E2E pass/fail |
| **Environment** (0.18) | ServiceNow, Kubernetes, Terraform, VMware | REST API / CMDB | Component provisioning status, stability, drift |
| **Dependency** (0.13) | JIRA, ServiceNow, Team APIs | REST API | Cross-team dependency status, integration test outcomes |
| **Operability** (0.07, planned) | Jenkins, GitHub Actions, ArgoCD | REST API | Pipeline health, deployment success rate, runbook status |
| **Observability** (0.03, planned) | Dynatrace, Grafana, Splunk, Datadog | REST API | Dashboard coverage, alert configuration, trace sampling |

#### Tier 2: Gate-Only Dimensions (veto caps, no score)

| Dimension | Source System | Integration Type | Key Signals |
|-----------|--------------|-----------------|------------|
| **Security & Compliance** | Checkmarx, Veracode, Snyk, BlackDuck | REST API | SAST/DAST results, CVE counts, licence risk |
| **Performance** | Gatling, K6, JMeter, Dynatrace | File/API | Load test results, P99 latency vs SLO, capacity headroom |
| **Rollback** (planned) | Release management playbook DB | File/API | Rollback procedure status, tested/documented flag |
| **Accessibility** (planned) | Axe, Pa11y, BrowserStack | REST API | WCAG compliance gates |
| **Auditability** (planned) | GRC system, Confluence, ServiceNow | REST API | Audit log completeness, compliance artefact status |
| **Disaster Recovery** (planned) | DR runbook system, AWS/Azure | File/API | RTO/RPO tested, failover validated |
| **Data Reconciliation** (planned) | ETL platform, data quality tools | File/API | Migration row counts, checksum validation |
| **Failure Mode** (planned) | Incident management, chaos engineering | REST API | FMEA completion, chaos test outcomes |
| **Architecture Fitness** (planned) | ArchUnit, custom CLI | File | Architecture rule pass rate |
| **Architecture Drift** (planned) | Git, Backstage, dependency-track | REST API | Drift from intended design |

### 3.3 Integration Patterns

Three integration patterns are already in the codebase, addressing all source system types:

```
Pattern 1: PULL via FILE (current)
──────────────────────────────────
Source system exports JSON → placed in data/ directory → SourceReader reads on assessment run
Use for: batch exports, overnight feeds, CI pipeline artefacts
Latency: snapshot-accurate (as fresh as the last export)
Config:  { type: file, path: "./data/environment.json" }

Pattern 2: PULL via HTTP API (current — localhost only in Phase 1)
──────────────────────────────────────────────────────────────────
SourceReader calls HTTP GET → validates JSON → Pydantic InputContract
Use for: live APIs on the deployment host, localhost-only tools
Config:  { type: api, url: "http://127.0.0.1:9000/environment" }
Phase 2: relax allowed_hosts to include real API endpoints

Pattern 3: PUSH via INGEST (current — HTML only)
─────────────────────────────────────────────────
Source system exports HTML → rrr-ingest CLI batch-converts → brain/*.json
Use for: RKT, legacy portal exports, any system that can HTML-export
Extension path: add BrainWriter-compatible extractors for CSV, Excel, JIRA export

Pattern 4: PUSH via WEBHOOK (planned — not in roadmap yet)
───────────────────────────────────────────────────────────
CI/CD pipeline POSTs assessment trigger on deploy event → rrr API endpoint
Use for: event-driven assessment on every deployment
Requires: REST API wrapper around pipeline.py (FastAPI/Flask thin layer)
```

### 3.4 Integration Dependency Map

```
                    ┌──────────────────────────────────────────┐
                    │         INTEGRATION PREREQUISITES        │
                    │                                          │
  Phase 1           │  LOCAL DATA FILES (already done)         │
  (current)         │  ● brain/*.json from rrr-ingest          │
                    │  ● data/environment.json (manual)        │
                    │  ● data/dependency.json (manual)         │
                    │  ● data/operational.json (manual)        │
                    └──────────────────────────────────────────┘
                    ┌──────────────────────────────────────────┐
                    │     TEAM / PROGRAMME INTEGRATION         │
  Phase 2           │  ● SonarQube REST API for SQ metrics     │
  (enterprise       │  ● JIRA REST API for story points        │
   pilot)           │  ● Jenkins/GH Actions for pipeline       │
                    │  ● Security scanner (Checkmarx/Snyk)     │
                    │  ● ServiceNow CMDB for environment       │
                    └──────────────────────────────────────────┘
                    ┌──────────────────────────────────────────┐
                    │       PROGRAMME-WIDE INTEGRATION         │
  Phase 3           │  ● All of the above + more dimensions    │
  (programme        │  ● Centralised deployment (Kubernetes)   │
   asset)           │  ● Multi-tenant SQLite or PostgreSQL     │
                    │  ● SSO / LDAP for dashboard auth         │
                    │  ● Webhook from CI/CD pipeline           │
                    └──────────────────────────────────────────┘
```

---

## 4. Client Asset Positioning

### 4.1 The Asset Value Proposition

RRR is not a one-off tool. It is a **reusable release governance accelerator** that can be configured and deployed on any client engagement where software delivery is large enough to require a structured release process. The target clients are:

- Government and public sector programmes (DWP, HMRC, NHS-level complexity)
- Financial services transformation (banking, insurance core system replacements)
- Retail/telco platforms with multiple product teams releasing concurrently
- Any Accenture delivery engagement with ≥ 15 teams and ≥ 50 releases per quarter

### 4.2 What Makes It an Asset (Not a Custom Build)

The following design decisions, already in the codebase, make this a packagable asset:

| Design Decision | Asset-Ready Signal | Gap |
|----------------|-------------------|-----|
| All weights and thresholds in `default_config.yaml` | Full client customisation without code changes | — |
| `--config` CLI override | Client-specific config overlay supported | — |
| `TierThresholds` per release type | Supports hotfix vs major release governance variations | — |
| Named gate signals in config (`environment_down`, `dependency_failed`) | Gate behaviour configurable per client risk appetite | — |
| `LLMProvider` interface + pluggable backends | Client can choose local Ollama, Bedrock, or Claude | — |
| `AbstractAssessmentStore` | Backend swap (SQLite → PostgreSQL) without assessor changes | Remote store is a stub — needs real implementation |
| `InputContract` with `extra="ignore"` | Tolerates client-specific extra fields in source data | — |
| `BaseTool` protocol | New source integrations without modifying core | — |
| `BaseAssessor` ABC | New dimensions without modifying orchestrator | — |
| HTML export ingest | Works with any RKT-based programme | Only handles RKT format — other source systems need new extractors |
| NiceGUI dashboard | Ready-made interface for non-technical stakeholders | Authentication, multi-user, and RBAC not implemented |
| Jinja2 output templates | Report customisation without code changes | Template library is thin (one markdown, one plan, one HTML) |

### 4.3 Positioning Strategy — Three Client Engagement Models

#### Model A: Proof of Value (4-week engagement)
> Deploy RRR against one programme's existing RKT data. Configure weights to match client's release governance policy. Run assessments across all active releases. Deliver a programme health report and GO/NO-GO recommendation for the next release window.

**Deliverable:** Assessment results, trend dashboard, recommendation report.  
**Effort:** Minimal — ingest existing HTML exports, tune `default_config.yaml`, deploy locally.  
**Client value:** Immediate. They see objective data driving a decision that previously took a two-hour meeting.

#### Model B: Integrated Delivery Accelerator (3-month engagement)
> Wire RRR to the client's live source systems (SonarQube, JIRA, Jenkins, ServiceNow). Add client-specific assessor configurations. Provide the NiceGUI dashboard to the programme management office. Automate nightly brain refresh.

**Deliverable:** Functioning release governance system integrated with client toolchain.  
**Effort:** 4–6 weeks engineering + 2–4 weeks configuration and rollout.  
**Client value:** Removes the manual release readiness meeting from the delivery calendar permanently.

#### Model C: Enterprise Release Governance Platform (6–12 month engagement)
> Full deployment on client cloud (AWS/Azure), multi-tenant (one instance per programme), integrated with enterprise IAM, feeding into programme-level executive dashboards. Includes custom assessors for client-specific compliance requirements.

**Deliverable:** Enterprise platform operated by the client (with Accenture AMS support).  
**Effort:** Full platform engineering + change management.  
**Client value:** Standardised release governance across the entire delivery portfolio.

### 4.4 Accenture IP Protection Considerations

When packaging for client delivery:
- All client source system adapters should be written as installable plugins (not in core)
- Default weights and thresholds should be documented as "Accenture baseline" with client-customisable overrides
- The evaluation harness (golden fixtures + Hypothesis property tests) is IP — do not hand over to the client
- The ADR library is an artefact of architectural decision-making and should be included in the handover as evidence of decision quality

---

## 5. Plug-and-Play Architecture Assessment

### 5.1 Current Pluggability Inventory

The system demonstrates genuine plug-and-play extensibility in three dimensions:

#### Dimension 1: Provider Plugins (LLM backends)
```python
# Adding a new provider requires:
# 1. Implement LLMProvider ABC (reason() method)
# 2. Add ProviderType enum value
# 3. Add config block in schema.py
# 4. Add dispatch case in pipeline.build_provider()
# Zero changes to assessors, orchestrator, or output layer.
```
**Pluggability rating: 9/10.** The interface is clean, the guardrail chain wraps any provider automatically, and the fallback to `RuleBasedProvider` is transparent.

#### Dimension 2: Assessor Plugins (new dimensions)
```python
# Adding a new assessor requires:
# 1. Extend BaseAssessor, implement dimension property + _assess()
# 2. Add DimensionName enum value
# 3. Add to WeightsConfig (or mark gate-only weight=0)
# 4. Add source reader or tool
# 5. Add to assessor list in pipeline.assess()
# Zero changes to orchestration, scoring, or verdict logic.
```
**Pluggability rating: 8/10.** The pattern is solid. Gap: adding a new weighted assessor requires a weights config change that invalidates the sum-to-1.0 constraint — requires a coordinated change to `default_config.yaml`. Gate-only assessors are simpler to add (no weight rebalancing needed).

#### Dimension 3: Source System Plugins (new data integrations)
```python
# Adding a new source system requires:
# 1. Implement BaseTool protocol (invoke() method)
# 2. Add FileSource or ApiSource config support
# 3. Validate into an InputContract model
# Zero changes to assessors that use existing tool protocol.
```
**Pluggability rating: 7/10.** The protocol is clean. Gap: each new source system requires a new `InputContract` model and a new `SourceReader` class — there is no generic source adapter or schema-mapping layer. For enterprise scale, a source-system plugin registry (autodiscovery via entry points) would be needed.

### 5.2 What Is Missing for True Plug-and-Play

| Gap | Impact | Complexity to Fix |
|-----|--------|-------------------|
| No assessor autodiscovery | Adding a new assessor requires modifying `pipeline.py` | Medium — use Python entry points or a `@register_assessor` decorator |
| No tenant isolation | One config file per deployment means no multi-client | High — requires a TenantContext abstraction |
| No source plugin registry | New source systems require core code changes | Medium — entry_points in pyproject.toml for `rrr.source_readers` |
| No authentication on NiceGUI dashboard | Anyone with network access sees all data | High — must add before any client deployment |
| No REST API surface | Can only be called from CLI or Python | High — blocks webhook and CI/CD integration patterns |
| No schema migration | SQLite schema fixed at creation | Medium — add Alembic or a `PRAGMA user_version` guard |
| No configuration validation UI | Config errors only caught at runtime | Low — add `rrr config validate` CLI command |

---

## 6. Deep Component Analysis

### 6.1 Ingest Layer (`src/rrr/ingest/`)

**Purpose:** Anti-corruption boundary (ADR-0018) — converts raw HTML from RKT Program Metrics into the typed brain contract JSON consumed by all assessors.

**Architectural assessment:**

✅ **Correct pattern:** The extractor is the only place that knows the RKT HTML structure. All downstream code is insulated from HTML format changes.

✅ **Robust extraction:** Uses regex against the `__REPORT__` JavaScript literal rather than DOM parsing — correct choice for embedded JSON in HTML; tolerant of whitespace variation.

✅ **Idempotent writes:** `BrainWriter.append_snapshot()` upserts on snapshot date — safe to re-run on the same HTML export.

✅ **TOC value-stream tagging (ADR-0021):** Correctly parses the TOC slide to identify the value stream, allowing the UI to group by programme.

⚠️ **Format coupling risk:** The `__REPORT__` pattern is tightly coupled to the RKT HTML export format. If RKT changes its export structure, the extractor breaks with no fallback. Mitigation: add an integration test that validates the extractor against a pinned HTML fixture.

⚠️ **Single source system:** Currently handles only RKT HTML. A client that uses JIRA + Confluence for the same data has no ingest path. Each new source requires a bespoke extractor.

❌ **No streaming support:** The extractor loads the full HTML into memory. For very large programme exports (50+ releases, 12 months of history), this could exceed available memory on constrained hosts.

**Recommendation:** Add a `BaseExtractor` ABC with `extract(source_path)` → `(date, releases)` interface. Register extractors by format type. This enables future JIRA, CSV, and API-pull extractors without modifying `BrainWriter`.

---

### 6.2 Brain Contract & Data Models (`src/rrr/models/`)

**Purpose:** Typed data contracts for all cross-boundary data flows. Two postures: frozen `RRRModel` for outputs (closed schema), mutable `InputContract` for upstream data (tolerant schema).

**Architectural assessment:**

✅ **Two-posture model is architecturally sound.** `extra="forbid"` on outputs catches schema drift immediately. `extra="ignore"` on inputs tolerates upstream additions without breaking assessments.

✅ **Full type coverage.** All 18 model files have complete type annotations — mypy strict passes cleanly. This is significantly better than most Python projects at this stage.

✅ **Enum centralisation.** All controlled vocabularies in `models/enums.py`. No magic strings crossing module boundaries.

✅ **Field descriptions.** Every field has `Field(description="...")` — the descriptions double as prompt context for LLM calls and documentation.

⚠️ **Schema version is pinned at "1.0.0" with no migration path.** `AssessmentOutputModel.schema_version` is a string constant. There is no version negotiation logic in `SQLiteAssessmentStore`. If the schema evolves (e.g., the tier fields added in this milestone), old SQLite records will deserialise with missing fields and raise a Pydantic `ValidationError`. This is a latent data corruption risk.

⚠️ **No protobuf or Avro contract.** The brain contract is JSON with Pydantic validation. For multi-system integration at enterprise scale, a more formal IDL (protobuf, JSON Schema with versioning, or OpenAPI) would allow cross-language validation.

❌ **`BrainHistory.snapshots` is a list — no deduplication guard at the model level.** Two snapshots with the same date are valid according to the model. Deduplication is enforced only in `BrainWriter.append_snapshot()`. A `@model_validator` could add this invariant at the model level.

**Recommendation:** Add a `SchemaRegistry` with version-aware deserialisation. At minimum, add `migration_notes` to `AssessmentOutputModel` and a `load_with_migration(raw_dict)` factory that can apply field-level defaults for missing fields from older schema versions.

---

### 6.3 Configuration Layer (`src/rrr/config/`)

**Purpose:** Single source of truth for all tunable parameters. YAML-based with Pydantic v2 validation. Merging semantics: bundled defaults + optional client override file.

**Architectural assessment:**

✅ **Deeply validated.** `RRRConfig` uses `@model_validator` cross-field checks throughout. The `SourcesConfig` model validator enforces the localhost-only constraint on API hosts at load time — security policy enforced as a data invariant, not runtime code.

✅ **`TiersConfig` is well-designed.** The `for_tier()` method returns the correct `TierThresholds` without any runtime type narrowing issues (fixed with explicit annotation in this milestone).

✅ **`WeightsConfig` sum-to-1.0 validator** is a critical invariant that prevents misconfiguration from silently distorting scores.

⚠️ **No config hot-reload.** The config is loaded once at startup. For a long-running server deployment (rrr-ui, future REST API), changing weights or thresholds requires a process restart. This is acceptable for Phase 1 but is a gap for enterprise operations.

⚠️ **The `allowed_hosts` list defaults to `["127.0.0.1", "localhost"]` but is not enforced at the TCP layer.** It is checked in `SourcesConfig` at config-load time (preventing misconfiguration) and in `source_reader.py` at invocation time. However, if an allowed host resolves to an external IP via DNS, the check passes. A true network control requires OS-level egress filtering or a service mesh policy.

⚠️ **No config schema documentation.** `default_config.yaml` has inline comments but no published JSON Schema or OpenAPI Schema for the config file. Client engineers have no tooling-assisted authoring experience.

❌ **No environment variable override.** All config comes from YAML. Enterprise deployments commonly inject secrets and environment-specific values via environment variables (e.g., `RRR_PROVIDER_TYPE=claude`, `RRR_ANTHROPIC_API_KEY=...`). This requires a config merge layer that supports `os.environ` overrides — important for Kubernetes secrets injection.

**Recommendation:** Add `ConfigLoader.from_env_overrides()` that reads `RRR_*` prefixed environment variables and merges them into the config after YAML loading. Export a JSON Schema from `RRRConfig.model_json_schema()` as a build artefact for IDE auto-complete support.

---

### 6.4 Tools Layer (`src/rrr/tools/`)

**Purpose:** Protocol-based abstraction over all external data reads. Uniform timeout enforcement and audit recording for every tool invocation.

**Architectural assessment:**

✅ **`BaseTool` as a `@runtime_checkable Protocol`** is the correct Python 3.8+ idiom for structural subtyping. Any object with `name` and `invoke()` satisfies the protocol — no inheritance needed for simple adapters.

✅ **Every invocation produces a `ToolInvocationModel`** regardless of success or failure. This is the audit trail requirement (NFR-3) correctly enforced at the infrastructure level, not at the business logic level.

✅ **Timeout enforcement via daemon thread** is pragmatic and correct for I/O-bound tool calls. The daemon thread guarantees no zombie thread survives process termination.

⚠️ **Retry policy is primitive.** `retry_count` and `retry_backoff_s` in `ToolsConfig` apply uniformly to all tools. A JIRA API retry should have exponential backoff; a local file read should not retry at all. A per-tool retry strategy would be more appropriate at enterprise scale.

⚠️ **No circuit breaker.** If a source API is consistently failing (e.g., SonarQube is down during an assessment run), the tool retries `retry_count` times, records the failure, and the assessor marks itself unavailable. This is correct behaviour but it means every assessment run attempts the dead endpoint. A circuit breaker with a time-windowed failure counter would short-circuit failed tools faster in a high-frequency deployment.

❌ **`ToolRunner` is stateless and does not cache.** Each assessor invocation of the same tool causes a new HTTP request or file read. In a programme with 50 releases being assessed in sequence, the `EnvironmentSourceReader` will be called 50 times against the same data file. A session-scoped tool result cache keyed on `(tool_name, params_hash)` would eliminate redundant I/O.

**Recommendation:** Introduce a `ToolResultCache` context manager in the orchestrator fan-out path that caches tool results within a single assessment run. This is the single highest-leverage performance improvement available today.

---

### 6.5 Assessors (`src/rrr/assessors/`)

**Purpose:** One assessor per dimension. Template method pattern via `BaseAssessor`. Deterministic scoring in `_assess()`, LLM narrative in `reason()`.

**Architectural assessment:**

✅ **Template method pattern is correctly applied.** The base class owns the orchestration contract: `reset()` → `_assess()` → `reason()` → assemble `DimensionResult`. Subclasses cannot break the ordering.

✅ **`DeterministicAssessment` dataclass** cleanly separates the numeric computation output from the reasoning phase. Assessors cannot accidentally use LLM output to compute scores.

✅ **Severity-to-gate mapping is consistent.** All eight assessors correctly assign CRITICAL → NO_GO gate, MAJOR → CONDITIONAL gate, MINOR → informational. The `gate` field on `RiskFactor` is used by `GateEngine` for named gate lookup (ADR-0014) with severity as fallback (ADR-0013). This two-level gate resolution is elegant.

✅ **Confidence formula is uniform.** BaseAssessor computes confidence from tool outcomes: all pass = 1.0, any fail = ≤ 0.5, all fail = 0.0. This is applied after `_assess()` returns, so subclasses cannot inflate confidence.

⚠️ **`OperationalAssessor` is scheduled for splitting (ADR-0016 item 7) but not yet split.** The current 0.10 weight conflates three distinct concerns: deployment pipeline health (operability), monitoring/alerting coverage (observability), and rollback readiness. These have different data sources, different risk profiles, and different gate requirements per tier. The split is architecturally correct and should be prioritised.

⚠️ **`TestReadinessAssessor` is the highest-weight assessor (0.27) and also the most complex.** It is a composite of three sub-signals (quality, defect trend, E2E pass rate) with configurable weights and an E2E-absent fallback path. The complexity is justified by the domain but makes the assessor harder to tune and harder to explain to a client. A per-sub-signal evidence breakdown in the `DimensionResult` would improve interpretability.

⚠️ **Nine planned gate-only assessors have no input models yet.** `AccessibilityAssessor`, `AuditabilityAssessor`, `DisasterRecoveryAssessor`, `DataReconciliationAssessor`, `FailureModeAssessor`, `DependencyRiskAssessor`, `ProductionReadinessAssessor`, `ArchitectureFitnessAssessor`, `ArchitectureDriftAssessor` are listed in `docs/assessor_inputs.md` and `default_config.yaml` but have no Pydantic `InputContract` models, no `SourceReader` implementations, and no assessor code. This is a significant remaining build. Each requires input contract design, data source integration, scoring logic, and tests.

❌ **`ScopeAssessor` uses `sq_avg` from the brain contract** (a SonarQube Quality Gate average), but `TestReadinessAssessor` also uses `sq_avg` and `sq_below_1`. There is duplication of data access — both assessors read the same field from the same brain record independently. This is not a bug (each assessor gets its own `BrainReadResult`) but it means both assessors are scored and reasoned on the same underlying data. A `SharedToolResultCache` would eliminate the redundant read.

**Current weight distribution analysis:**

```
TestReadiness  0.27  ████████████████████████████ (dominant — defensible given test quality is the primary risk signal)
Scope          0.23  ████████████████████████
Environment    0.18  ██████████████████
Dependency     0.13  █████████████
Operational    0.10  ██████████   ← split pending (Operability 0.07 + Observability 0.03)
Estimation     0.09  █████████
               ────
               1.00

Gate-only (no weight, but veto via CRITICAL/MAJOR risk factors):
Security       0.00  ──── veto only
Performance    0.00  ──── veto only
+ 9 planned           ──── all veto only
```

The weight distribution is defensible for a software delivery programme. Test quality and scope completion carry the most predictive power for release outcomes. The Estimation weight (0.09) is appropriately modest — estimation accuracy predicts process maturity, not safety.

---

### 6.6 Orchestration Engine (`src/rrr/orchestration/`)

**Purpose:** Fan-out assessors in parallel, fuse scores, derive verdict. LangGraph wrapper for optional tracing.

**Architectural assessment:**

✅ **`ThreadPoolExecutor` for fan-out** is the correct choice for I/O-bound assessors. The GIL does not impede I/O. Each assessor's tool reads (file or HTTP) block independently without interfering with others.

✅ **`Orchestrator.collect()` is publicly callable** — the LangGraph wrapper calls it without reimplementing the collection logic. This resolved a ~80-line duplication and is the right design.

✅ **`derive_verdict()` applies caps in the correct order:** INCOMPLETE check first (data quality gate), then score band, then risk factor caps, then required-dimension guard, then confidence floor. The order matters and is correct.

✅ **`GateEngine.apply()` has two resolution paths** — named gate lookup (preferred, config-driven) and severity fallback (always present). This means a misconfigured gate name silently falls back to severity behaviour rather than failing, which is safe and graceful.

✅ **`split_scores()` cleanly separates** ship-safety (TEST_READINESS + ENVIRONMENT + DEPENDENCY) from delivery-performance (SCOPE + ESTIMATION). These are the two questions a CAB wants answered: "Is it safe to ship?" and "Did we deliver what we planned?"

⚠️ **`_fan_out()` uses a fixed timeout** (`assessor_default: 300s`) applied to all assessors equally. A slow `PerformanceAssessor` that hits a local Gatling report API will block for 5 minutes before timing out, delaying the whole assessment. Per-assessor timeout config would be more precise.

⚠️ **`score_over_snapshots()` in `ui/app.py`** runs full pipeline assessments for every brain snapshot date in the Trends tab. For a programme with 12 months of weekly snapshots (52 data points) × 40 releases = 2,080 mini-assessments per Trends render. This is computationally expensive and not cached. The UI freezes on large datasets.

❌ **No distributed coordination.** If two instances of the CLI run simultaneously against the same SQLite database, there is a write contention risk. `SQLiteAssessmentStore` has a retry policy (`retry_attempts=3`) on locked DB writes, but the retry window is 5 × 3 = 15 seconds. A WAL-mode SQLite connection would reduce contention significantly.

❌ **`run_assessment_graph()` vs `Orchestrator.run()`** — the graph entry point is the canonical one called from `pipeline.py`, but it delegates directly to `Orchestrator.run()` when LangGraph is not installed. This means the tracing/visualisation benefit of LangGraph is opt-in and invisible in the default deployment. For a client engagement, this distinction should be made explicit in the deployment guide.

**Recommendation:** Enable SQLite WAL mode in `SQLiteAssessmentStore.__init__()` with a single `PRAGMA journal_mode=WAL`. This is a one-line change that eliminates write contention for all concurrent CLI usage patterns.

---

### 6.7 Provider Abstraction (`src/rrr/providers/`)

**Purpose:** Pluggable LLM backends. Guardrail chain: validate → repair → fallback to `RuleBasedProvider`.

**Architectural assessment:**

✅ **The guardrail chain (ADR-0009) is architecturally mature.** Parse → repair (1 retry) → fallback is the minimal viable safety net that prevents LLM output failures from breaking assessments. The `RuleBasedProvider` fallback is always available and always correct.

✅ **Injection safety in `ReasoningRequest`** correctly separates data (`facts: list[str]`) from instructions (`summary`, `allowed_classifications`). Raw tool output never flows into instruction fields.

✅ **`ClaudeProvider` (Phase 2)** uses `claude-opus-4-8` default, configurable. The `max_tokens` and `temperature` are in config. This is correctly designed for a Phase 2 opt-in.

✅ **`BedrockProvider` (Phase 2)** uses the Bedrock Converse API (the correct multi-model API, not a model-specific API). This supports regional data residency — important for UK/EU government clients.

⚠️ **`LocalLLMProvider` uses stdlib `urllib`** rather than the `ollama` SDK. This is intentional (keeping the core dependency list minimal) but means the Ollama API contract is hardcoded — if Ollama changes its endpoint schema, the provider breaks silently. The optional `[local-llm]` group installs the `ollama` SDK but it is not used.

⚠️ **`MockLLMProvider` reads fixture files from disk.** For a CI environment with a read-only filesystem or a containerised deployment, the fixture path must be configured explicitly. The default path is relative — it will fail if the working directory is not the project root.

⚠️ **No token budget awareness.** Each provider call passes `max_tokens` from config. For long narratives (many risk factors, complex rationale), the LLM may hit the token limit and return a truncated response. The guardrail chain will attempt to parse the truncated response, likely fail validation, retry, and fall back to `RuleBasedProvider`. The fallback is safe but the token truncation is invisible to the caller.

❌ **No prompt versioning.** The reasoning prompt template is embedded in each assessor's `_build_request()` method (or the base class). If the prompt changes, there is no record of which prompt version produced which assessment. For audit purposes, the `AuditTrail` should include a `prompt_version` hash.

**Recommendation:** Add `prompt_version: str` to `AuditTrail` — a short hash of the prompt template used. This is a low-effort change with high audit value.

---

### 6.8 Memory & Persistence (`src/rrr/memory/`)

**Purpose:** SQLite local store (primary), optional Chroma vector index (similar-release lookup), remote store stub (Phase 2).

**Architectural assessment:**

✅ **`AbstractAssessmentStore` ABC** correctly defines the contract that both local and remote implementations must satisfy. The `build_store()` factory in `pipeline.py` is the single dispatch point — callers never construct stores directly.

✅ **`SQLiteAssessmentStore` stores the full `AssessmentOutputModel` as JSON** in a `document` column alongside indexed metadata columns (`release`, `value_stream`, `verdict`, `score`, `generated_at`). This is the correct dual-storage pattern: fast queries on indexed columns, full fidelity from the JSON document.

✅ **Chroma integration is optional and degrades silently** if `chromadb` is not installed. The `similar_to()` method returns an empty list when Chroma is unavailable — a safe, documented degradation.

⚠️ **The SQLite schema has no version control.** There is no `PRAGMA user_version` guard, no migration script, no schema validation on open. If the schema evolves (e.g., adding a `tier` column to the metadata index), existing databases will not be automatically migrated.

⚠️ **The `document` column stores the full `AssessmentOutputModel` JSON without compression.** An assessment record with 8 dimensions, each with full evidence and tool invocations, can easily exceed 50 KB. For 1,000 assessments across a programme's lifetime, this is 50 MB — manageable. For a multi-client shared deployment with 100,000 assessments, this is 5 GB of uncompressed JSON in a single SQLite file. Compression or field pruning for the document store should be considered.

⚠️ **`RemoteAssessmentStore` raises `NotImplementedError` on every method.** This is a correct stub pattern, but `build_store()` will return this stub if `config.memory.backend == "remote"`, causing runtime failures. The config should validate that remote backend is not selected in Phase 1 until a real implementation exists.

❌ **No backup or export mechanism.** The SQLite database is the only persistent record of all assessments. There is no `rrr export` CLI command, no automated backup, and no mention of backup in the deployment guide. For an enterprise client, this is a critical gap — a corrupted SQLite file loses all historical assessment data.

**Recommendation:** Add a `rrr export --format jsonl` CLI command that streams all assessment records to a JSONL file. This provides a simple backup mechanism and an offline analytics feed.

---

### 6.9 Collectors (Planned) (`src/rrr/collectors/`)

**Status:** The `collectors/` directory does not yet exist. ADR-0023 (Proposed, 2026-07-04) defines the intent: a `rrr-collect` CLI and interactive data collection screen in the UI.

**Architectural assessment of the planned design:**

The collector concept fills a real gap: currently, assessment data for environment, dependency, operational, security, and performance dimensions must be placed in `data/*.json` files manually. In a client engagement, an engineer must populate these files before each assessment run. This is the primary friction point preventing RRR from being a fully self-service tool.

The planned architecture (ADR-0023) is sound in principle. The key design questions that must be answered before implementation:

1. **Pull vs push model:** Should `rrr-collect` pull data from source APIs, or should CI/CD pipelines push data to RRR via a REST endpoint? Pull requires credentials in the RRR config. Push requires a REST server. The current architecture strongly favours pull (consistent with local-first ADR-0010).

2. **Collection failure handling:** If the environment source API is down during collection, should `rrr-collect` fail, warn, or use cached data? The assessor graceful degradation handles unavailable data at assessment time, but the collection layer needs its own failure policy.

3. **Authentication for source APIs:** `rrr-collect` will need API keys, OAuth tokens, or service account credentials for each source system. These must not be stored in the YAML config in plaintext. A `SecretProvider` abstraction (reading from environment variables, AWS Secrets Manager, or Azure Key Vault) is required.

**Recommendation:** Before implementing ADR-0023, create an `InputContract` model and a `BaseCollector` ABC. The `BaseCollector` should have a `collect(release, config)` → `InputContract` interface and a `pre_flight_check()` → `bool` method. This gives the `CollectorRunner` a consistent protocol and ensures the collection layer follows the same patterns as the assessor layer.

---

### 6.10 Web UI Dashboard (`src/rrr/ui/app.py`)

**Purpose:** NiceGUI-based web dashboard for non-technical stakeholders. Five screens: Overview, Release Detail, History, Trends, Ingest.

**Architectural assessment:**

✅ **Data helper functions are pure Python** and do not import NiceGUI. They are independently unit-testable (10 tests cover them). This is the correct separation of concerns — the UI layer is a thin rendering shell over data functions.

✅ **Overview screen prioritises risk** — NO_GO releases appear first, then CONDITIONAL, then GO, then unassessed. This is the correct default for a release readiness tool.

✅ **Release Detail screen is comprehensive.** The scrollable single-page layout with verdict hero → dimension scorecard → risk factors → rationale → remediation → source metrics → history is a well-structured information hierarchy that a release manager can scan in under 30 seconds.

✅ **Programme-first selection model (ADR-0022)** with TOC value-stream grouping is a thoughtful UX decision — it mirrors how clients think about their delivery portfolio (by programme, then by value stream, then by release).

⚠️ **No authentication.** The NiceGUI server binds to `127.0.0.1:8080` by default, which limits exposure in Phase 1. But any client-facing deployment (even within a client VPN) requires at minimum HTTP Basic Auth or SSO integration. A production deployment without authentication is a security gap.

⚠️ **`score_over_snapshots()` re-runs full pipeline assessments for Trends.** This is computationally expensive (see §6.6 performance note). For a client with 40 releases and 52 snapshots, the Trends tab is effectively unusable without caching.

⚠️ **NiceGUI runs on a single-threaded async event loop.** Computationally expensive operations (full assessment, trend computation) must not block the event loop. Currently, `score_over_snapshots()` is called synchronously. This will freeze the dashboard for all users during a Trends render.

❌ **No RBAC.** Release managers, programme directors, and engineering teams should see different views. A programme director should see portfolio-level KPIs. A release manager should see release-level detail. An engineer should see dimension-level evidence. The current UI shows everything to everyone.

❌ **NiceGUI is not suitable for large-scale concurrent use.** It is a Python-native UI framework optimised for local or small-team use. For a client engagement with 200 users accessing the dashboard concurrently, a JavaScript frontend (React/Vue) with a REST API backend would be more appropriate.

**Recommendation:** For Phase 1 (small team, local deployment), NiceGUI is acceptable. For client deployment, create a FastAPI REST API layer (`/api/v1/releases`, `/api/v1/assessments`, `/api/v1/trends`) and a React/Vue frontend. NiceGUI can remain as the admin/development interface.

---

### 6.11 Pipeline & CLI Composition Root

**`pipeline.py` assessment:**

✅ **`pipeline.py` is the single composition root.** All wiring happens here — tools, assessors, provider, store. No other module performs dependency injection.

✅ **`assess()` and `run_and_record()` separation** correctly isolates pure computation (assess) from stateful persistence (record). Tests can call `assess()` without a store.

⚠️ **All eight assessors are constructed unconditionally** even if a source is not configured. Security and Performance are opt-in (checked via `config.sources.security` / `config.sources.performance`) but all other assessors are always constructed. If a client has not configured the environment source, `EnvironmentAssessor` will be constructed, will fail its tool call, and will be marked unavailable. This is correct behaviour but wasteful — consider lazy assessor construction.

**`cli.py` assessment:**

✅ **Exit codes** (GO=0, NO_GO=1, CONDITIONAL=2, ERROR=3) make RRR a natural CI/CD pipeline gate — `if rrr --release "X"; then deploy; fi` works natively.

✅ **Fuzzy release matching** avoids the most common user error (slightly wrong IR name). The `--list-releases` flag gives users a reference list.

⚠️ **`--programme` flag** is available at the CLI level but filters only the release list. It does not constrain which brain snapshot is used. A client with multiple programmes in the same brain file could inadvertently assess a release from the wrong programme if they omit the flag.

⚠️ **`--format html`** generates a Bootstrap 5 page that loads CDN assets. This requires internet access on the rendering machine — inconsistent with the local-first (ADR-0010) principle. The Bootstrap CSS/JS should be bundled or inlined.

---

### 6.12 Output Layer

**Current output formats:** `text`, `json`, `markdown`, `plan`, `html`

✅ **Jinja2 templating** (Markdown, Plan, HTML) is the correct approach — separates rendering logic from data.

⚠️ **Template library is thin.** One markdown template, one plan template, one HTML template. For a client engagement, the release manager report, the CAB submission template, and the executive dashboard KPI export would each need their own template.

⚠️ **No PDF output.** Many governance processes require a signed PDF. A `--format pdf` option (via `weasyprint` or `reportlab`) would be a high-value addition.

❌ **No machine-readable diff output.** When comparing two assessments (this week vs last week), there is no `--format diff` that shows changed scores and newly triggered gates. The `TrendData` model has this information but the output layer doesn't expose it as a diff format.

**Recommendation:** Add `--format pdf` as a Phase 3 output format. It requires a single optional dependency (`weasyprint`) and the HTML template already provides the content foundation.

---

### 6.13 Test Architecture

**Test counts and distribution:**

| Layer | Files | Coverage quality |
|-------|------:|-----------------|
| Unit tests | 27 files | High — every assessor, provider, model, and tool has dedicated tests |
| Property tests (Hypothesis) | 1 file | Medium — covers scoring invariants; could cover more assessor properties |
| Golden fixture tests | 5 fixtures (g1–g5) | High — all five verdict paths (GO, NO_GO, CONDITIONAL, INCOMPLETE, CONDITIONAL-via-creep) are covered |
| Eval tests (LLM-as-judge) | 5 files | Medium — structural judge implemented; prose quality judge implemented |

**Architectural assessment:**

✅ **Golden fixtures as ground truth.** The five fixture directories are the oracle for regression testing. Each new scoring change must update the `ideal.json` oracle — this discipline prevents silent score regression.

✅ **Hypothesis property tests** cover the six most critical invariants: score in [0,1], weight normalisation to 1.0, verdict determinism, INCOMPLETE condition, CRITICAL → NO_GO cap, and band monotonicity. These are the properties that must never break.

✅ **506 tests all passing** at 20 seconds total is an excellent signal. The test suite is fast enough to run in CI on every commit.

⚠️ **No integration tests against real source APIs.** All tests mock the file reads or use golden fixtures. A real SonarQube or JIRA API endpoint is never hit in tests. This means integration regressions (API endpoint change, auth header format change) are invisible until a client deployment fails.

⚠️ **No mutation testing.** Hypothesis catches property violations but does not verify that the test assertions themselves are strong enough to catch bugs. A `mutmut` or `cosmic-ray` run would identify weak assertions.

❌ **No load test.** There is no test that verifies the performance of a full assessment run against a realistic data set (40 releases, 52 snapshots). The Trends tab performance gap (§6.10) was identified by analysis, not by a test.

**Recommendation:** Add `tests/integration/test_live_sources.py` with pytest marks (`@pytest.mark.live`) that skip unless `RRR_LIVE_TESTS=1` is set. These tests hit a local Ollama instance and a real SonarQube API to verify the end-to-end integration path.

---

## 7. Well-Architected Framework Review

### 7.1 Operational Excellence

**Rating: 7/10**

#### Strengths
- **Infrastructure as code for config:** All operational parameters in `default_config.yaml`. Config changes are version-controlled, reviewable, and rollback-able.
- **Full audit trail:** Every tool invocation, every gate triggered, every provider call is recorded in `AuditTrail`. Post-incident investigation has the full evidence chain.
- **Structured output:** JSON output format enables log aggregation and alerting on verdict changes without log parsing.
- **Exit codes in CLI:** CI/CD pipelines can make deployment decisions directly from `rrr` exit codes without parsing output.
- **ADR library:** 23 decision records capture the "why" behind every significant architectural choice. Operational runbooks can reference these.

#### Gaps
- **No operational runbook.** There is no document describing how to diagnose a failed assessment, restart a hung assessor, or recover from a corrupt SQLite database.
- **No health check endpoint.** The NiceGUI dashboard has no `/health` endpoint that a load balancer or monitoring system can probe.
- **No metrics emission.** Assessment duration, assessor failure rate, provider fallback rate, and verdict distribution are computed but not emitted as metrics (Prometheus, OpenTelemetry). An operations team has no way to set an alert on "provider fallback rate > 10%."
- **No structured logging.** `pipeline.py` uses `print()` statements and Click's `echo()`. A production deployment needs structured JSON logging with correlation IDs (one ID per assessment run).
- **No process supervision.** The `rrr-ui` server runs as a foreground process. There is no systemd unit file, Docker health check, or Kubernetes liveness probe specification.

**Actions required:**
1. Replace `print()` calls with `logging.getLogger("rrr")` with structured formatters.
2. Add OpenTelemetry SDK as an optional dependency (`rrr[observability]`). Emit a span per assessor, with score and confidence as span attributes.
3. Add `/health` and `/metrics` endpoints to `rrr-ui` (NiceGUI supports custom FastAPI routes).
4. Write an `ops/runbook.md` covering the five most common operational scenarios.

---

### 7.2 Security

**Rating: 6/10**

#### Strengths
- **Local-first (ADR-0010):** No external network calls at runtime in Phase 1. Attack surface is minimal.
- **API host allow-list:** Enforced at config-load time as a Pydantic validator. Misconfigured API endpoints are rejected before any network call.
- **Prompt injection defence (ADR-0009):** Data and instructions are separated in `ReasoningRequest`. Raw user or tool output never flows into instruction fields.
- **No secrets in code:** API keys are read from environment variables or config, not hardcoded.
- **`extra="forbid"` on output models:** Prevents unexpected fields from flowing through the system from LLM responses.

#### Gaps
- **No authentication on `rrr-ui`.** The dashboard runs unauthenticated. On a client network, any user who can reach the port can see all release data, risk factors, and remediation plans — which may include sensitive information.
- **No TLS.** NiceGUI runs on HTTP by default. All dashboard traffic is unencrypted. This is acceptable for `127.0.0.1` but not for any networked deployment.
- **API keys in YAML config.** The `ClaudeConfig` and `BedrockConfig` blocks accept API keys via config file, which may be checked into version control. The config should support environment variable interpolation for secrets.
- **No input sanitisation at the CLI boundary.** The `--release` flag accepts arbitrary user input which is passed to `RKTBrainReader.read()`. If the brain reader uses the release name to construct a file path, this could be a path traversal vector. The current implementation uses it as a dictionary key lookup, which is safe, but this is not enforced by the type system.
- **Bootstrap CDN in HTML output.** `--format html` loads Bootstrap from a CDN. In a client environment with strict CSP or no internet access, this output is broken or is a CSP violation.
- **No RBAC.** All users see the same view. A contractor should not see security posture details for another team's release.
- **SQLite file permissions.** The `rrr.sqlite` file is created in `./data/local/` with default OS permissions. On a shared host, other users can read the assessment database.

**Actions required:**
1. Add HTTP Basic Auth to NiceGUI as a configuration option (`ui.basic_auth_user`, `ui.basic_auth_password`).
2. Support `${ENV_VAR}` interpolation in YAML config values for secrets injection.
3. Add a `--sanitise` flag to `rrr export` that redacts risk factor descriptions before sharing output.
4. Bundle Bootstrap CSS inline in the HTML template to eliminate CDN dependency.
5. Set `0600` permissions on the SQLite file at creation.

---

### 7.3 Reliability

**Rating: 8/10**

This is the strongest pillar. The multi-layer graceful degradation model (ADR-0005, ADR-0009) is well-designed and consistently implemented.

#### Strengths
- **Four-layer degradation:** Tool failure → assessor unavailable → weight redistributed → verdict still produced. The system never crashes on partial data.
- **`minimum_assessors` guard:** INCOMPLETE verdict is returned if too few dimensions are available — the system refuses to produce a GO/NO-GO with insufficient evidence.
- **Guardrail chain:** LLM output validated → repaired → fallback to `RuleBasedProvider`. Provider failures degrade to deterministic output, not crashes.
- **Timeout enforcement:** Every tool call has a configurable timeout. Hung external APIs do not block the assessment indefinitely.
- **Retry policy on SQLite writes:** Handles database lock contention gracefully.

#### Gaps
- **No circuit breaker.** Persistent source API failures retry on every assessment run. A time-windowed failure counter would reduce noise.
- **No distributed lock.** Concurrent CLI invocations can cause SQLite write contention. WAL mode mitigates but does not eliminate this.
- **`RemoteAssessmentStore` is a stub.** If configured, the system fails at runtime. The config should prevent this.
- **No data freshness enforcement.** An assessment can run against a brain snapshot that is 6 months old. The `freshness_max_age_days` config option applies only to `TestReadinessAssessor`. A global `brain_freshness_max_age_days` check at pipeline entry would prevent stale assessments.

**Actions required:**
1. Enable SQLite WAL mode: `PRAGMA journal_mode=WAL` in `SQLiteAssessmentStore.__init__()`.
2. Add a global freshness check in `pipeline.assess()` that warns (not fails) if the brain snapshot is older than a configurable threshold.
3. Add a `backend_not_implemented` validator in `ConfigLoader` that raises `ConfigurationError` if `backend == "remote"` in Phase 1.

---

### 7.4 Performance Efficiency

**Rating: 5/10**

This is the weakest pillar. The system is performant for its current local use case (one assessment per CLI invocation, one user on the dashboard), but has several scalability issues that will surface in enterprise deployment.

#### Critical Performance Issues

**Issue 1: `score_over_snapshots()` — O(releases × snapshots) full pipeline runs**
```
For a typical large programme:
  40 releases × 52 weekly snapshots = 2,080 full assessments
  Each assessment: 8 assessors × 300s timeout (max) = unbounded
  In practice: ~0.5s per assessment (local, rule_based) = ~17 minutes per Trends render

Mitigation: Cache assessment results per (release, snapshot_date) in SQLite.
            The Trends tab should query the cache, not re-run assessments.
```

**Issue 2: No tool result cache within an assessment run**
```
If 50 releases are assessed in sequence (e.g., rrr-collect batch mode):
  Each release reads environment.json separately = 50 file reads of the same file
  Each release calls SonarQube API separately = 50 API calls for shared data

Mitigation: Session-scoped ToolResultCache keyed on (tool_name, params_hash).
            This is O(1) memory for file reads and O(requests) for API calls.
```

**Issue 3: NiceGUI event loop blocking**
```
score_over_snapshots() is called synchronously in the Trends tab render path.
This blocks the NiceGUI async event loop for the duration of all assessments.
All other dashboard users are frozen during this time.

Mitigation: Run score_over_snapshots() in a background thread via
            asyncio.run_in_executor() and update the chart progressively.
```

**Issue 4: ThreadPoolExecutor assessor concurrency is unbounded**
```
All 8 assessors (and eventually 19) run concurrently. If all are fast,
this is fine. If any block on I/O for the full assessor_default (300s),
the assessment hangs for 5 minutes. There is no backpressure mechanism.

For 19 assessors all timing out: 19 concurrent threads each holding for 300s.
This could exhaust thread pool resources on a constrained host.

Mitigation: Add max_workers parameter to ThreadPoolExecutor (e.g., min(19, cpu_count * 2)).
            Per-assessor timeouts (from config) rather than uniform timeout.
```

#### Performance Benchmarks (current state, estimated)

| Operation | Current | Target | Notes |
|-----------|---------|--------|-------|
| Single release assessment (RuleBasedProvider) | ~0.5s | <0.5s | Already fast |
| Single release assessment (LocalLLMProvider) | ~15-30s | <10s | LLM latency dominant |
| Single release assessment (ClaudeProvider) | ~5-10s | <5s | API latency dominant |
| Trends tab render (40 releases, 12 snapshots) | ~4 min | <5s | Needs caching |
| Full programme batch (40 releases) | ~20s | <10s | Parallelise batch |
| SQLite write (single assessment) | <1ms | <1ms | Already fast |
| Dashboard load (Overview, 40 releases) | <1s | <1s | Already fast |

**Actions required (prioritised by impact):**

1. **High:** Cache assessment results in SQLite by `(release, snapshot_date)`. Trends tab queries cache. Add `--force-refresh` to bypass cache.
2. **High:** Session-scoped `ToolResultCache` for file reads in batch assessment mode.
3. **Medium:** Run `score_over_snapshots()` in a background thread with progress indicator.
4. **Medium:** Add `max_workers=min(len(assessors), os.cpu_count() * 2)` to `ThreadPoolExecutor`.
5. **Low:** Per-assessor timeout configuration in `AssessorsConfig`.

---

### 7.5 Cost Optimization

**Rating: 8/10 (Phase 1) / 5/10 (Phase 2 projection)**

#### Phase 1 (Local-Only) — Cost Profile

| Resource | Cost | Notes |
|----------|------|-------|
| CPU | Negligible | 8 assessors × ~0.1s CPU per assessment |
| Memory | ~100 MB | Python process + Pydantic models + brain data |
| Storage | ~50 MB/year | SQLite assessments (compressed: ~5 MB/year) |
| Network | Zero | Local-only |
| LLM | Zero | `RuleBasedProvider` by default |
| Infrastructure | Zero | Runs on developer laptop |

Phase 1 is essentially zero-cost to operate.

#### Phase 2 (LLM-Enabled) — Cost Risk Areas

**Risk 1: LLM token cost per assessment**
```
Each assessment makes N+1 provider calls:
  N = number of assessors (8 currently, 19 planned)
  1 = verdict synthesis

With ClaudeProvider (claude-opus-4-8):
  Per assessor: ~500 tokens in + ~300 tokens out = ~800 tokens
  Per assessment: 9 × 800 = ~7,200 tokens
  Cost at $15/M input + $75/M output:
    Input: 9 × 500 × $15/1M = $0.068
    Output: 9 × 300 × $75/1M = $0.203
    Total: ~$0.27 per assessment

At 100 assessments/day × 250 working days: $6,750/year
At 1,000 assessments/day: $67,500/year

Mitigation: Use LocalLLMProvider (Ollama) for all non-executive-facing assessments.
            Reserve ClaudeProvider for weekly executive report generation only.
```

**Risk 2: No token usage budgeting**
```
There is no per-tenant or per-programme token budget.
A single runaway batch job could exhaust a client's API quota in minutes.

Mitigation: Add TokenBudget to ProviderConfig (max_tokens_per_day, max_cost_per_day).
            Track usage in AssessmentStore. Fail gracefully (fall back to RuleBasedProvider)
            when budget is exhausted.
```

**Risk 3: Chroma embedding cost**
```
Chroma generates embeddings for each saved assessment via the default embedding function.
At 1,000 assessments, this is 1,000 embedding calls.
If using a cloud embedding API (OpenAI, Cohere), this adds ~$0.001 per assessment.

Mitigation: Use Chroma's built-in local embedding model (sentence-transformers).
            This is the current default — the risk is only if the embedding provider
            is changed to a cloud API.
```

#### Cost Optimisation Recommendations

1. **Tiered provider policy:** `RuleBasedProvider` for batch/automated runs, `LocalLLMProvider` for interactive CLI, `ClaudeProvider` only for executive-facing reports.
2. **Assessment caching:** Avoid re-assessing the same (release, snapshot) pair. Cache hit = zero LLM cost.
3. **Prompt length optimisation:** Reduce the number of `facts` passed to the LLM. Each assessor currently passes all evidence records as facts. Filtering to the top 5 most impactful facts would cut token usage by ~40% with negligible quality loss.
4. **Batch API usage:** For ClaudeProvider, use the Anthropic Batch API (50% cost reduction) for non-realtime assessment jobs.
5. **Token budget enforcement:** Add `max_cost_usd_per_run` to `ProviderConfig`. Track cost in `AuditTrail`.

---

### 7.6 Sustainability

**Rating: 7/10**

#### Strengths
- **Local-first by default:** No cloud GPU inference = zero carbon from LLM calls in Phase 1.
- **Lightweight runtime:** Python process, SQLite, no containerisation required. Can run on a developer laptop. No always-on cloud infrastructure needed.
- **Efficient data model:** The brain contract is a compact JSON snapshot, not a full RDBMS dump. Storage is minimal.

#### Gaps
- **Phase 2 cloud LLM calls** have a non-trivial carbon footprint. A single Claude Opus call has an estimated carbon cost of 0.5–2g CO₂e. At 100 assessments/day, that is 50–200g CO₂e/day — modest but non-zero.
- **Chroma's default embedding model** (`all-MiniLM-L6-v2`) runs local inference — sustainable. If replaced with a cloud API, the footprint increases.
- **NiceGUI dashboard in a browser** has minimal rendering cost — correct for a data-light application.

**Recommendation:** Add a `--provider rule_based` override for automated batch runs to ensure zero LLM carbon cost for programmatic use cases. Reserve cloud LLM for human-interactive sessions only.

---

## 8. Architectural Strengths

### 8.1 Deterministic-First Invariant (ADR-0006, ADR-0017)

This is the system's single most important design decision. By confining the LLM exclusively to narrative generation and bounding its classification space via `allowed_classifications`, the system produces verdicts that:
- Are **reproducible** without an LLM
- Are **explainable** to non-technical stakeholders without referencing AI
- Pass **regulatory scrutiny** (SOX, ISO 27001, FCA) that prohibits AI black-box decisions
- Are **resilient** to LLM failures (narrative degrades, verdict stands)

No commercial release governance tool reviewed has this property.

### 8.2 Anti-Corruption Boundary (ADR-0012, ADR-0018)

The strict separation between the RKT HTML format and the typed brain contract is textbook Domain-Driven Design. The `HTMLExtractor` is the only component that knows the RKT structure. All downstream components are insulated. When RKT changes its export format, only one file needs to change.

### 8.3 Pydantic v2 Everywhere (ADR-0004)

The consistent use of Pydantic v2 models across all data boundaries (input contracts, output models, LLM I/O, config) eliminates an entire class of runtime bugs. The mypy strict compliance (63 source files, zero issues) is a signal of exceptional Python type discipline.

### 8.4 ADR-Driven Development

23 Architecture Decision Records provide an unbroken record of every significant design choice. This is a maintainability asset that is rare in Python projects and a genuine quality signal for client confidence.

### 8.5 Multi-Tier Graceful Degradation

Four independent degradation layers mean the system never crashes on partial data. A client whose environment API is temporarily down still gets an assessment — with Environment marked unavailable, weight redistributed, and a confidence-capped result. This is production-grade reliability thinking applied to a Python CLI.

### 8.6 Test Architecture

506 tests covering unit, property (Hypothesis), golden fixture, and LLM-as-judge evaluation layers in 20 seconds is exceptional. The golden fixture pattern (five verdict scenarios with oracle `ideal.json` files) provides regression protection that survives weight changes and algorithm evolution.

---

## 9. Architectural Gaps and Risks

### 9.1 Critical Gaps (block enterprise deployment)

| # | Gap | Risk | Mitigation |
|---|-----|------|------------|
| C1 | No authentication on `rrr-ui` | Sensitive release data exposed to any network user | Add HTTP Basic Auth + TLS as a config option |
| C2 | No multi-tenancy | Cannot serve multiple client programmes from one instance | Add `TenantContext` with per-tenant config, store, and brain path |
| C3 | SQLite WAL mode not enabled | Write contention in concurrent deployments | Single `PRAGMA journal_mode=WAL` in store init |
| C4 | Trends tab O(n×m) performance | Dashboard freezes with realistic data volumes | Cache assessment results by (release, snapshot_date) |
| C5 | No secret injection support | API keys must be in YAML — risk of version control exposure | Add `${ENV_VAR}` interpolation in `ConfigLoader` |

### 9.2 Significant Gaps (block production readiness)

| # | Gap | Risk | Mitigation |
|---|-----|------|------------|
| S1 | No SQLite schema migration | Schema evolution corrupts old records | Add `PRAGMA user_version` guard and migration scripts |
| S2 | No structured logging | Operational diagnosis requires log parsing | Replace `print()` with `logging.getLogger("rrr")` |
| S3 | No health/metrics endpoints | No monitoring integration possible | Add `/health` and expose OpenTelemetry metrics |
| S4 | No backup mechanism | SQLite loss = all historical data lost | Add `rrr export` command |
| S5 | `rrr-collect` not implemented | All env/dep/security data requires manual JSON files | Implement ADR-0023 |
| S6 | OperationalAssessor not split | Conflates operability, observability, rollback | Implement ADR-0016 item 7 |
| S7 | 9 planned gate-only assessors not built | Key governance dimensions (accessibility, DR, etc.) missing | Systematic build per ADR-0016 items 8–16 |

### 9.3 Design Risks (architecture could degrade)

| # | Risk | Trigger | Mitigation |
|---|------|---------|------------|
| D1 | Weight distribution becomes stale | New dimensions added without holistic rebalancing | Require an ADR for any weight change affecting sum-to-1 invariant |
| D2 | LLM narrative boundary erodes | Future provider added that includes a score in its response | The guardrail chain catches this — but the test suite should include a property that asserts LLM response never contains a numeric score |
| D3 | SQLite becomes a bottleneck | > 100,000 assessments in a single database | Add `rrr migrate --backend postgres` path before this is needed |
| D4 | Golden fixture oracle drift | Score algorithm changes without updating `ideal.json` | CI gate: `pytest tests/golden/` must run on every commit that touches `orchestration/` or `assessors/` |

---

## 10. Strategic Recommendations

### 10.1 Immediate Actions (before next client engagement)

**Priority 1 — Security hardening (1 week)**
- Add HTTP Basic Auth to NiceGUI: `app.add_middleware(BasicAuthMiddleware, credentials=config.ui.credentials)`
- Add `${ENV_VAR}` interpolation in `ConfigLoader` for API key secrets
- Enable SQLite WAL mode (one-line change)
- Set `0600` permissions on SQLite file at creation

**Priority 2 — Performance foundation (1 week)**
- Implement `ToolResultCache` context manager in `Orchestrator._fan_out()`
- Add assessment cache in `SQLiteAssessmentStore` with `(release, snapshot_date)` key
- Move `score_over_snapshots()` to background thread in NiceGUI

**Priority 3 — Operational observability (1 week)**
- Replace `print()` with structured `logging`
- Add `correlation_id` to `AuditTrail`
- Add `/health` endpoint to `rrr-ui`
- Write `ops/runbook.md`

### 10.2 Medium-Term Actions (M7 / Phase 2)

**Collector layer (ADR-0023 implementation — 2–3 weeks)**
- `BaseCollector` ABC with `collect()` + `pre_flight_check()` interface
- `CollectorRunner` with parallel execution and failure isolation
- `SecretProvider` abstraction for credential management
- `rrr-collect` CLI with `--status` and `--all` flags
- UI Collect screen with `InputContract`-driven forms

**REST API layer (new ADR — 2 weeks)**
- FastAPI wrapper over `pipeline.assess()` and `run_and_record()`
- Endpoints: `POST /api/v1/assess`, `GET /api/v1/releases`, `GET /api/v1/history/{release}`, `GET /api/v1/health`
- This enables webhook-triggered assessments from CI/CD pipelines
- This is the single most impactful integration investment for enterprise adoption

**Multi-tenancy (new ADR — 3 weeks)**
- `TenantContext` dataclass: `tenant_id`, `config`, `store`, `brain_dir`
- Tenant registry in a shared SQLite or PostgreSQL
- `rrr-ui` tenant switcher in the header
- Per-tenant config overlay files

### 10.3 Strategic Actions (Phase 3 / Enterprise Asset)

**Deployment packaging**
- Helm chart for Kubernetes deployment with configurable replicas, resource limits, and persistent volume for SQLite
- Docker Compose for single-host deployment (rrr-ui + optional Ollama sidecar)
- `rrr-server` command that starts a production-grade ASGI server (uvicorn + gunicorn)

**Enterprise integration playbook**
- Per-source-system integration guide: JIRA, SonarQube, Jenkins, ServiceNow, Checkmarx, Dynatrace
- Reference implementation for each collector
- Architecture pattern reference: pull-based vs push-based vs event-driven

**Report customisation framework**
- Jinja2 template extension point for client-specific report formats
- `rrr-ui` white-labelling (logo, colour scheme, client name in header)
- PDF output via `weasyprint`

---

## 11. Achievability Assessment

### 11.1 Current State Assessment

The system is further advanced than most AI-augmented tooling projects at the same stage. The deterministic-first invariant, the full Pydantic type coverage, the ADR library, the 506-test suite, and the five golden fixture scenarios all demonstrate architectural discipline that is ready for client demonstration.

**Phase 1 verdict: COMPLETE.** The system correctly produces GO/NO-GO/CONDITIONAL/INCOMPLETE verdicts with full audit trails. This is demonstrable to a client today.

**Phase 2 (in progress) verdict: ON TRACK.** M6 risk tiers are complete. OperationalAssessor split is clearly scoped. The nine planned gate-only assessors are documented with input contracts in `docs/assessor_inputs.md`.

### 11.2 Completion Roadmap Assessment

| Milestone | Scope | Estimated Sessions | Risk |
|-----------|-------|-------------------|------|
| M6 complete | OperationalAssessor split (items 7) + 9 new gate-only assessors (items 8–16) | 8–10 sessions | Medium — 9 new assessors × 3 components each (model, assessor, tests) |
| M7 complete | `rrr-collect` CLI + CollectorRunner + UI Collect screen | 4–6 sessions | Medium — ADR-0023 Proposed, design not finalised |
| Security hardening | Auth, TLS, secret injection, WAL mode | 1–2 sessions | Low |
| REST API layer | FastAPI wrapper + OpenAPI spec | 2–3 sessions | Low — the pipeline.py composition root is already the right shape |
| Multi-tenancy | TenantContext + tenant registry | 3–4 sessions | High — touches config, store, UI, CLI simultaneously |
| Enterprise deployment | Helm, Docker Compose, rrr-server | 2–3 sessions | Low — packaging is straightforward given the clean composition root |

**Total remaining estimate to enterprise-asset-ready: 20–28 sessions.**

### 11.3 The Single Biggest Risk

The most significant project risk is not technical — it is **weight credibility**. The dimension weights (`test_readiness: 0.27`, `scope: 0.23`, etc.) are currently set by the project team without empirical validation against historical release outcomes. A client programme director will inevitably ask: "Why is test readiness 27% of the score? What evidence do you have that this is the right weight?"

Without a calibration study against historical releases (e.g., "In retrospect, which dimension was most predictive of production incidents in our programme?"), the weights are assumptions. The evaluation harness (ADR-0008, `tests/eval/`) is the vehicle for this calibration. Making a calibration study against real client data a deliverable of the first client engagement would transform the system from an opinionated tool to an evidence-based one.

---

## 12. Appendix: ADR Maturity Scorecard

| ADR | Title | Status | Implementation Confidence |
|-----|-------|--------|--------------------------|
| 0001 | Record Architecture Decisions | Accepted | ✅ Fully operational — 23 ADRs demonstrate the practice |
| 0002 | LangGraph for Agent Orchestration | Accepted | ✅ ThreadPoolExecutor confirmed as production path; LangGraph is optional tracing layer |
| 0003 | SQLite for Persistence | Accepted | ✅ Built — gaps: WAL mode, schema migration |
| 0004 | Pydantic v2 | Accepted | ✅ Fully operational — all 63 modules, mypy clean |
| 0005 | Graceful Degradation | Accepted | ✅ Fully operational — four degradation layers |
| 0006 | LLMProvider Abstraction | Accepted | ✅ Five providers built — gaps: token budget, prompt versioning |
| 0007 | Chroma Vector Store | Accepted | ✅ Built inside store.py — optional, degrades silently |
| 0008 | Evaluation — Golden Dataset + LLM-Judge | Accepted | ✅ Built — gap: no calibration study against real incident data |
| 0009 | Guardrails + Repair Loop | Accepted | ✅ Fully operational |
| 0010 | Local-First Phase 1 | Accepted | ✅ Enforced at config-load time |
| 0011 | Dimension Weight Split | Accepted | ✅ Built — gap: weights not empirically calibrated |
| 0012 | Brain Input Contract | Accepted | ✅ Fully operational |
| 0013 | Verdict Veto/Cap Gates | Accepted | ✅ Fully operational |
| 0014 | Centralized Gate Engine | Accepted | ✅ Built — two-resolution-path design is elegant |
| 0015 | Required Dimensions + Confidence Floor | Accepted | ✅ Built |
| 0016 | Assessment Model v2 | Proposed | 🟡 Items 1–6 built; items 7–16 planned |
| 0017 | Make AI Earn Its Place | Accepted | ✅ Built — deviation: narrative-only; no classification adjudication |
| 0018 | HTML Ingest | Accepted | ✅ Built — gap: single source system |
| 0019 | Bedrock Provider | Accepted | ✅ Built — Phase 2 opt-in |
| 0020 | NiceGUI Dashboard | Accepted | ✅ Built — gaps: auth, performance, RBAC |
| 0021 | TOC Value-Stream Tagging | Accepted | ✅ Built |
| 0022 | Programme-First Selection | Accepted | ✅ Built |
| 0023 | Data Collection CLI | Proposed | ⬜ Not yet built |

---

*Review prepared by: Senior AI Enterprise Architect*  
*Based on codebase state as of: 2026-07-09*  
*Next review recommended at: M6 completion (estimated M7 entry)*
