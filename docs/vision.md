# Vision — Release Readiness Results (RRR)

## Problem Statement
Release GO/NO-GO decisions are often made on gut feel, scattered spreadsheets, and
incomplete information. Program metrics exist (in the upstream **RKT Program Metrics**
system) but are not synthesized into a single, defensible release verdict, and they
ignore key dimensions like environment readiness and dependency health.

RRR solves this for **release managers, program leads, and delivery teams** by turning
existing metrics plus new assessment dimensions into a **data-driven, auditable
GO / NO-GO / CONDITIONAL / INCOMPLETE verdict**.

## Goals
- Produce a single scored release verdict from multiple independent assessment dimensions.
- Be genuinely **AI-first**: delegate the judgment (ambiguous evidence, risk factors,
  rationale, remediation) to a pluggable **`LLMProvider`** while keeping the **score
  deterministic**.
- Be **local-first**: Phase 1 runs entirely on the user's machine with **no external
  calls** — a rule-based provider needs no model, an optional local LLM gives the AI-first
  demo. Scaling outside (Claude API, live data) is a Phase-2 opt-in, no rewrite (ADR-0010, ADR-0006).
- Reuse existing `brain/*.json` snapshots from RKT Program Metrics (no duplicate data entry).
- Add two net-new dimensions: **environment readiness** and **dependency tracking**.
- Make every conclusion traceable: verdict → dimension scores → evidence → tool invocations → LLM prompts.
- Degrade gracefully — a partial failure (or a bad LLM output) still yields a usable verdict, never a total crash.
- Persist every assessment so readiness **trends** can be compared, and **RAG over history** for benchmarking.
- Ship as a zero-config, file-based CLI that runs anywhere Python 3.11+ runs.

## Demo posture
The **demo runs locally** with the `LocalLLMProvider` (on-machine LLM) to show AI-first
behavior end to end; the `RuleBasedProvider` proves graceful degradation and fully
offline operation with no model required. Supporting docs: [architecture.md](architecture.md),
[adr/](../adr/), [evaluation-plan.md](evaluation-plan.md), and [ai-usage.md](ai-usage.md).

## Alternatives Explored & Excluded

Before committing to the current design, several alternative approaches were considered and
explicitly rejected. This section documents those trade-offs for architectural reviewers.

| Alternative | Why Excluded |
|-------------|-------------|
| **Web Dashboard (primary UI)** | Requires hosting, browser, network stack — contradicts local-first. The CLI gives zero-install access everywhere Python runs; a web layer is Phase 2 (M5) when scale-out is justified. |
| **Slack / Teams Bot** | A notification channel, not a synthesis engine. It could carry the verdict but cannot perform the assessment. Defers the hard problem (multi-dimension scoring) without solving it. |
| **Single heuristic score** | RKT Program Metrics already publishes a summary score. A second single number adds nothing. The value is in the five-dimension breakdown and the auditable reasoning behind each score. |
| **Pure rules engine (no LLM)** | Fully deterministic, but the verdict would be a score with no explanation. Release managers need "why" — borderline classifications, remediation priorities, and narrative justification require judgment, not just thresholds. The `RuleBasedProvider` is the graceful-degradation fallback, not the target. |
| **Pure LLM verdict** | Non-reproducible: same inputs can yield different labels on different runs. Violates the audit requirement (every release must be comparable). ADR-0006 hard-separates score (code) from reasoning (LLM) precisely to avoid this. |
| **Cloud SaaS / managed LLM API (default)** | Requires external network access at runtime. Many enterprise release environments are air-gapped or subject to data-residency rules. Local-first (ADR-0010) is a hard constraint for Phase 1; cloud is opt-in Phase 2. |
| **Real-time / continuous monitoring** | Assessment is intentionally on-demand (run before a release gate). Continuous monitoring adds alert fatigue, webhook complexity, and a stateful daemon — none of which the release-gate use case needs. |
| **CI/CD gate enforcer (primary role)** | Exit codes (0=GO, 1=NO_GO, 2=CONDITIONAL, 3=ERROR) make CI integration possible, but RRR is an *assessment tool*, not a pipeline step. Making it a gate enforcer by default would remove human review from the release decision — the opposite of the intent. |

## Non-Goals
- Not a replacement for RKT Program Metrics — RRR is a downstream **consumer** of it.
- Not a data-collection tool; it assesses data that already exists.
- No real-time monitoring or alerting (assessment is run on demand).
- Web dashboard is **Phase 2 / M5** (external scale-out) and explicitly out of scope for the initial CLI.
- Not a CI/CD gate enforcer (though exit codes make integration possible later).

## Success Metrics
- A full 5-dimension assessment completes in well under the configured timeouts.
- Verdict is reproducible: same inputs → same score and verdict.
- ≥ `minimum_assessors` (default 3) dimensions can fail and still produce a verdict.
- 100% of conclusions are backed by a navigable audit trail.
- Release managers can answer "why this verdict?" without leaving the tool output.

## Stakeholders
| Role | Responsibility |
|------|----------------|
| Release Manager | Owns the GO/NO-GO decision; primary consumer of the verdict |
| Program Lead | Reviews trends, scope, and estimation health across releases |
| Delivery / QA Teams | Provide test & environment readiness inputs; act on remediation plans |
| Platform / DevOps | Provide environment and dependency data (file or live API) |
| RKT Program Metrics (upstream system) | Source of `brain/*.json` scope, estimation, and test data |
