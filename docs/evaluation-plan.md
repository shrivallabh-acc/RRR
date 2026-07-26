# Evaluation Plan — Release Readiness Results (RRR)

How RRR's output quality is measured: golden dataset, success metrics (completeness,
accuracy, F1), and one automated evaluation (LLM-as-judge).
See [adr/0008-evaluation-golden-dataset-llm-judge.md](../adr/0008-evaluation-golden-dataset-llm-judge.md).

## 1. What "success" means
RRR succeeds when, given a release's data, it produces (a) the **correct verdict**,
(b) the **right risk factors**, and (c) an **actionable, faithful remediation plan** —
reproducibly, with an audit trail. The evaluation measures each of these against a
hand-curated golden standard.

## 2. Golden dataset (3–5 samples)
Stored under `tests/golden/`. Each sample is a realistic release fixture plus its ideal output:

| Sample | Scenario | Ideal verdict |
|--------|----------|---------------|
| `g1_clean_release` | All dimensions healthy | GO |
| `g2_failing_tests` | Strong scope/estimation, E2E pass rate well below threshold | NO_GO |
| `g3_borderline` | Mixed: partial scope, minor env gaps, deps at-risk | CONDITIONAL |
| `g4_missing_data` | Only 2 assessors have usable data | INCOMPLETE |
| `g5_scope_creep` | Delivery good but significant scope creep + estimation bias | CONDITIONAL |

Each sample directory contains:
- `inputs/` — `brain/*.json` + environment/dependency files (the system's input)
- `ideal.json` — `{ verdict, dimension_scores (tolerances), expected_risk_factors[], ideal_remediation }`, manually written

## 3. Metrics
| Dimension of quality | Metric | How computed |
|----------------------|--------|--------------|
| **Verdict accuracy** | Accuracy + **macro-F1** over {GO, NO_GO, CONDITIONAL, INCOMPLETE} | predicted vs `ideal.verdict` across all samples |
| **Score fidelity** | MAE per dimension vs ideal (within tolerance) | deterministic — must be stable run-to-run |
| **Risk detection** | Precision / Recall / **F1** | predicted risk factors vs `expected_risk_factors` (semantic match) |
| **Remediation completeness** | Completeness % | fraction of ideal remediation points covered |
| **Narrative quality** | LLM-as-judge score (0–1) | faithfulness, completeness, actionability |

Verdict accuracy and score fidelity are the **gating** metrics (they must be high and
reproducible); narrative quality is **diagnostic**.

## 4. Automated evaluation — LLM-as-judge
`tests/eval/judge.py` runs offline (not in the assessment hot path):
1. Run RRR on each golden sample → `AssessmentOutputModel`.
2. Deterministically compute verdict accuracy/F1, risk F1, score MAE.
3. For narrative/remediation, call **Claude as judge** (structured output, Pydantic-scored)
   comparing generated text against `ideal.json` on faithfulness / completeness /
   actionability, each 0–1 with a one-line justification. May use `claude-sonnet-4-6`
   for cost.
4. Emit an evaluation report (JSON + Markdown) with per-sample and aggregate scores.

## 5. Property-based tests (kept alongside — invariants, not quality)
`tests/property/` with Hypothesis, asserting:
- every dimension score ∈ [0.0, 1.0]; overall score ∈ [0.0, 1.0]
- weight redistribution preserves normalization (weights of available dims sum to 1.0)
- verdict mapping is monotonic in score (higher score never yields a worse verdict)
- `calculate_confidence()` bounds: any tool fail ⇒ ≤0.5; all fail ⇒ 0.0 + INCOMPLETE
- determinism: same inputs ⇒ identical score and verdict label

## 6. Acceptance thresholds (initial, tunable)
- Verdict macro-F1 ≥ 0.8 on the golden set
- Risk-factor F1 ≥ 0.7
- Remediation completeness ≥ 0.8
- LLM-as-judge narrative score ≥ 0.75 mean
- 100% determinism on score + verdict label across repeated runs
