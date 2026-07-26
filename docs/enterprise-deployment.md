# Enterprise Deployment — Release Readiness Results (RRR)

> **Audience:** Enterprise architects, RDE/FDE practitioners, delivery leads evaluating RRR for
> client engagement adoption. This document describes how RRR fits into the Accenture RDE operating
> model, how it would be deployed at a large enterprise client, and what uplift it leaves behind.

---

## 1. Client Persona

**Target client:** Mid-to-large enterprise with a maturing digital delivery practice. Typically:
- 10–50 delivery pods releasing software every 2–4 weeks
- Release governance currently dependent on manual spreadsheets, judgment calls, and email approvals
- Existing metrics system (or a system like RKT Program Metrics) producing raw delivery data
- Release managers who cannot explain "why GO?" to auditors beyond "it felt ready"

**Pain points addressed by RRR:**
| Pain point | RRR response |
|---|---|
| GO/NO-GO decisions are opaque | Auditable verdict with navigable evidence chain per dimension |
| Metrics exist but are not synthesized | 5-dimension weighted assessment from existing data |
| LLM tools are feared as a black box | Deterministic score + LLM narrative that explains each risk factor |
| Can't run AI tools in air-gapped environments | Local-first Phase 1; no external calls at runtime |
| Release risk accumulates silently across sprints | SQLite trend comparison + Chroma RAG over history |

---

## 2. The 90-Day RDE Execution Cycle

RRR maps directly to the Accenture RDE pod construct and 90-day delivery rhythm.

| Phase | Week | Activity | RRR role |
|---|---|---|---|
| **Embed** | 1–2 | Understand client's delivery process, metrics tooling, and release governance | Baseline assessment (RuleBasedProvider, zero AI risk) to establish current verdict distribution |
| **Configure** | 3–4 | Wire RRR to the client's brain-extract pipeline; configure weights for their risk profile | `default_config.yaml` tuning: dimension weights, gate caps, freshness thresholds |
| **Calibrate** | 5–8 | Run RRR in shadow mode (alongside existing process, not gating) | Build golden dataset from 3–5 historical releases; author `ideal.json` oracles; verify eval metrics |
| **Shadow** | 9–10 | Present RRR verdict alongside human committee verdict for each release | Compare verdicts; tune config; identify systematic gaps |
| **Gate** | 11–12 | Enable RRR as a mandatory input to the release committee | Release committee reviews RRR output before voting; score + rationale in the meeting pack |
| **Uplift** | 13+ | Transition ownership to client team; enable LocalLLMProvider for AI narrative | Handover: config repo, brain-extract pipeline, trained golden dataset, operating runbook |

---

## 3. Data Source Mapping

RRR reads from three input types. The client's existing data systems are mapped to these contracts.

| RRR input | Contract | Typical client source |
|---|---|---|
| `brain/*.json` | `docs/brain-schema.md` — weekly snapshot JSON with scope, estimation, test data per value stream | Jira (story points), TestRail / Xray (test results), finance system (EV data) — extracted by the upstream RKT brain tool or equivalent |
| `environment.json` | `docs/env-dep-schema.md` — component provisioning + stability status | ServiceNow CMDB export, Terraform state file, or a local API on `127.0.0.1` |
| `dependency.json` | `docs/env-dep-schema.md` — upstream/downstream dependency completion + integration status | Jira dependency links, program board extract, API gateway health check |

**Data residency:** All data is processed locally (Phase 1 hard constraint, ADR-0010). No metrics
leave the client's environment. The brain extract, verdict database (SQLite), and vector store
(Chroma) live on the same machine or within the client's on-prem/VPC boundary.

---

## 4. Deployment Topology

### Phase 1 — Single-machine CLI (default)

```
┌─────────────────────────────────────────────────────┐
│  Release Manager's Workstation (or CI runner)        │
│                                                      │
│  brain/*.json ──► rrr --release "..." ──► verdict   │
│  environment.json     (local Python,     + audit     │
│  dependency.json       no network)       trail       │
│                                                      │
│  SQLite: ./data/local/rrr.sqlite (history + trends)  │
│  Chroma: ./data/local/chroma/    (RAG vectors)       │
└─────────────────────────────────────────────────────┘
```

### Phase 1 — Docker (single-machine, containerized)

```bash
# Build once
docker build -t rrr:latest .

# Run assessment — brain and db live in Docker volumes
docker run --rm \
  -v "$(pwd)/brain:/data/brain" \
  -v rrr_db:/data/local \
  rrr:latest rrr --release "Sprint 42 Release"
```

Full `docker-compose.yml` provided — includes optional Ollama sidecar for `LocalLLMProvider`.

### Phase 2 (Future) — Kubernetes / shared service

When a delivery organisation has multiple teams consuming RRR, the tool can be exposed as a
shared service. This is a Phase 2 / M5 concern and requires:
- Kubernetes pod with persistent volume claims for SQLite and Chroma
- Ingress + auth layer (not part of Phase 1)
- Optional: swap SQLite for a shared RDBMS behind the `AssessmentStore` interface

```
┌──────────┐    ┌───────────────────────────────────────────┐
│  Team A  │    │  RRR Shared Service (K8s Deployment)      │
│  brain/  │───►│                                           │
│  env/dep │    │  rrr-pod ──► SQLite PVC ──► trend data    │
└──────────┘    │            ──► Chroma PVC ──► RAG history  │
┌──────────┐    │            ──► Ollama pod ──► local LLM   │
│  Team B  │───►│                                           │
│  brain/  │    └───────────────────────────────────────────┘
└──────────┘
```

---

## 5. Client Capability Uplift Artifacts

By the end of a 90-day engagement, the client team owns:

| Artifact | Description |
|---|---|
| `brain-extract/` pipeline | Script or CI job that transforms the client's project management system into the `brain/*.json` schema (ADR-0012). Client can run this independently. |
| Tuned `config.yaml` | Dimension weights, gate caps, and thresholds calibrated against the client's release history. |
| Golden dataset | 5–10 historical releases with `ideal.json` oracles; used for regression testing when config changes. |
| `tests/eval/` harness | Verdict accuracy, score MAE, and risk-F1 metrics computed against the golden dataset. |
| Operating runbook | How to: run an assessment, interpret the output, tune thresholds, escalate a CONDITIONAL. |
| LLM rollout plan | If `LocalLLMProvider` or `ClaudeProvider` is enabled post-engagement: prompt guidelines, evaluation cadence, confidence-floor monitoring. |

---

## 6. AI Engineering Story for Interview / Review Panels

| Question | RRR answer |
|---|---|
| "How do you ensure the LLM doesn't make up risk factors?" | Deterministic scoring in `_assess()`; LLM only writes narrative/rationale. Pydantic `parse_with_repair` validates every response. The verdict label comes from the numeric score, never from LLM text. |
| "What happens if the LLM is unavailable or gives garbage?" | `RuleBasedProvider` is always the fallback. Repair loop retries once, then falls back with reduced confidence. The pipeline never crashes on a bad LLM response. |
| "Can this run in an air-gapped environment?" | Yes. Phase 1 makes zero external calls. `RuleBasedProvider` needs no model. `LocalLLMProvider` uses Ollama on `127.0.0.1`. |
| "How do you know the AI is adding value over a rules engine?" | The evaluation harness (`tests/eval/`) runs all 5 golden fixtures and computes verdict accuracy + score MAE. When a live LLM is enabled, the same harness compares LLM vs rule-based narrative quality via `judge.py` (Phase 2). Until that lift is demonstrated, the `RuleBasedProvider` is the honest default. |
| "How would you deploy this at scale?" | Phase 1: containerized CLI via Docker, each team runs their own instance, data stays local. Phase 2: Kubernetes shared service with PVCs for SQLite/Chroma + optional Ollama sidecar. Interface stays the same — no code rewrite to scale up. |
| "What's the 90-day story?" | Embed → configure brain-extract pipeline → calibrate thresholds on historical data → shadow GO/NO-GO committee → gate as required input → hand over with full golden dataset and runbook. |
