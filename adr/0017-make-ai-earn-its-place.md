# ADR 0017: Make the AI Earn Its Place — Bounded LLM Role + Eval-Gated Adoption

- **Status:** Accepted (implemented 2026-06-30; deviation noted in implementation note below)
- **Date:** 2026-06-16

## Context
RRR is positioned as **AI-first**, but as built that claim is currently hollow:
- With the default `RuleBasedProvider` there is **no model in the loop at all**.
- Even with a model, the LLM only writes prose — score, classification, and verdict are 100%
  deterministic, and classification of "ambiguous" items is itself computed deterministically in the
  assessors. So the `LLMProvider` seam risks never earning its complexity, and "AI-first" overstates
  what the system does.

This is not an argument to add AI to the *scoring* (ADR-0009 rightly forbids that). It is about
giving the LLM a **real, bounded, measurable** job — or being honest that it has none yet.

## Decision (proposed)
- **Bounded LLM job:** the LLM adjudicates **only borderline/ambiguous classifications within a
  deterministic band** (e.g. a completion ratio in a configurable grey zone), and owns the
  **quality of the remediation plan** — not the score, not the verdict label (ADR-0009 unchanged).
- **Eval-gated adoption:** the LLM path is adopted only where it shows **measured lift** over the
  `RuleBasedProvider` baseline, via the evaluation harness (FR-27) + LLM-as-judge (FR-28). Until lift
  is demonstrated on the golden set, position the product honestly as
  **"deterministic + explainable, AI-optional."**

## Consequences
- The "AI-first" claim becomes evidence-backed rather than aspirational, with an explicit success
  metric (lift vs baseline on accuracy / risk-F1 / remediation completeness / judge score).
- No change to determinism or the structured-output guardrails (ADR-0006/0009 hold).
- Sequencing: needs the **evaluation harness first** (M4), then a real provider (M5) to measure.

## Alternatives Considered
- **Drop the AI framing entirely** — rejected: there is genuine value in LLM judgment on borderline
  cases and in remediation prose, *if* it's measured rather than assumed.
- **Let the LLM influence the score/verdict** — rejected: non-reproducible, unauditable (ADR-0009).
- **Keep claiming AI-first with no measurement** — rejected: it's the exact "agent vocabulary over a
  rules engine" trap the project already caught once (see `docs/ai-usage.md` Stage 1).

## Implementation note — 2026-06-30

**Status: Accepted** (with one deliberate deviation from the proposed decision).

**What was built:**
- Each assessor makes exactly **one `LLMProvider` call** for the dimension narrative (prose
  explaining *why* the score is what it is). The orchestrator makes exactly **one** call for verdict
  rationale + remediation plan. This is the bounded, measurable job described in this ADR.
- **`ProseQualityJudge`** (`tests/eval/judge.py`, FR-28, ADR-0008) — live-LLM eval using
  `ClaudeProvider`; scores clarity, specificity, actionability, and evidence-grounding for each
  narrative. API-key guard keeps CI offline-safe. Eval threshold ≥ 0.70. FR-28 fully closed
  2026-06-26.
- **`StructuralJudge`** (`tests/eval/judge.py`) — offline CI-safe; checks narrative completeness,
  classification correctness, confidence range, and risk-factor coverage. Score 1.00 on all 5
  golden fixtures.
- The evaluation harness (`tests/eval/`) provides the measurable gate: verdict accuracy 100%,
  macro-F1 1.000, score MAE 0 (all 5 golden fixtures, 2026-06-17; prose judge 2026-06-26).

**Deviation: LLM classification adjudication not implemented.**
The proposed decision included "the LLM adjudicates borderline/ambiguous classifications within a
configurable grey zone." After building and verifying the deterministic assessors, this was
intentionally skipped. Rationale:
- The deterministic assessors already produce the correct classification in all 5 golden fixtures
  (verdict accuracy 100%, risk-F1 0.80 mean).
- Introducing LLM calls into the classification path would make scores non-reproducible and
  conflict with the deterministic-first invariant (ADR-0006/0009).
- The LLM "earns its place" through prose quality, not through score influence — this is a
  stronger interpretation of the spirit of this ADR, not a weakening of it.

**The "AI-first" claim is now evidence-backed:**
With `ClaudeProvider` (Phase 2 opt-in) and `ProseQualityJudge` as the measurement mechanism, RRR
positions correctly as *"deterministic + explainable, AI-optional"* with a concrete quality gate
rather than an aspirational claim.
