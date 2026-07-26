# RRR Evaluation Report

> Generated: 2026-06-23 08:47 UTC  
> Golden dataset: 5 fixtures (g1–g5)  
> Metric definitions: [docs/evaluation-plan.md](evaluation-plan.md)  
> ADR: [ADR-0008](../adr/0008-evaluation-golden-dataset-llm-judge.md)

---

## 1. Deterministic Metrics Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Verdict accuracy | 100.0% | 100% | ✅ |
| Macro-F1 | 1.000 | ≥ 0.80 | ✅ |
| Mean score MAE | 0.25 | lower is better | ℹ |
| Mean risk-factor F1 | 1.000 | ≥ 0.70 | ✅ |

## 2. Per-Fixture Verdict Results

| Fixture | Ideal | Predicted | Match | Score MAE | Risk F1 |
|---------|-------|-----------|-------|-----------|---------|
| g1_clean_release | GO | GO | ✅ | 0 | 1.00 |
| g2_failing_tests | NO_GO | NO_GO | ✅ | 0 | 1.00 |
| g3_borderline | CONDITIONAL | CONDITIONAL | ✅ | 0 | 1.00 |
| g4_missing_data | INCOMPLETE | INCOMPLETE | ✅ | — | 1.00 |
| g5_scope_creep | CONDITIONAL | CONDITIONAL | ✅ | 1 | 1.00 |

## 3. Structural Quality (LLM Output)

> Checks that narrative, classification, rationale, and remediation fields are
> present and non-empty.  Prose quality scoring requires a live LLM (Phase 2).

| Fixture | Narrative | Structural | Risk | Rationale | Remediation |
|---------|-----------|------------|------|-----------|-------------|
| g1_clean_release | 100% | 1.00 | 100% | ✅ | 0 |
| g2_failing_tests | 100% | 1.00 | 100% | ✅ | 3 |
| g3_borderline | 100% | 1.00 | 100% | ✅ | 2 |
| g4_missing_data | 100% | 1.00 | 100% | ✅ | 0 |
| g5_scope_creep | 100% | 1.00 | 100% | ✅ | 2 |
| **Mean** | — | **1.00** | **100%** | — | — |

## 4. Dimension Score MAE per Fixture

| Fixture | scope | estimation | environment | test_readiness | dependency |
|---------|-------|------------|-------------|----------------|-----------|
| g1_clean_release | 0.0003 | 0.0000 | 0.0000 | 0.0005 | 0.0000 |
| g2_failing_tests | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| g3_borderline | 0.0000 | 0.0000 | 0.0000 | 0.0004 | 0.0000 |
| g4_missing_data | — | — | 0.0003 | — | 0.0000 |
| g5_scope_creep | 0.0003 | 0.0000 | 0.0000 | 0.0031 | 0.0000 |

## 5. Quality Gate

| Check | Result |
|-------|--------|
| Verdict accuracy = 100% | ✅ PASS |
| Macro-F1 ≥ 0.80 | ✅ PASS |
| Mean risk-F1 ≥ 0.70 | ✅ PASS |
| Structural score ≥ 0.60 (all fixtures) | ✅ PASS |

**Overall: ✅ PASS**

---

## Methodology

**Deterministic metrics** (§1–2, §4) are pure math over the golden dataset — no LLM.
**Structural quality** (§3) checks LLM-written fields are present and non-empty.
**Prose quality scoring** (§4, when generated with `ANTHROPIC_API_KEY`) uses `ProseQualityJudge`
(`ClaudeProvider`, `claude-haiku-4-5-20251001`); scores clarity, specificity, actionability, and
evidence-grounding of each narrative. FR-28 fully closed 2026-06-26. See
[ADR-0008](../adr/0008-evaluation-golden-dataset-llm-judge.md). (Re-run `python -m tests.eval.run_eval` with `ANTHROPIC_API_KEY` set to populate §4.)

