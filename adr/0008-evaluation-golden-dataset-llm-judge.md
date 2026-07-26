# ADR 0008: Evaluation — Golden Dataset + F1 + LLM-as-Judge

- **Status:** Accepted (implemented 2026-06-26)
- **Date:** 2026-06-08

## Context
RRR's output quality must be measurable, not asserted: a golden dataset (3–5 samples with
ideal outputs), success metrics (completeness, accuracy, **F1**), and **one automated
evaluation** (keyword match or **LLM-as-judge**). Property-based tests (Hypothesis) verify
scoring *invariants* but do **not** measure the quality of the system's AI outputs — a
separate, explicit evaluation harness is needed.

## Decision
Build an evaluation harness (full design in [docs/evaluation-plan.md](../docs/evaluation-plan.md)):
- **Golden dataset**: 3–5 curated release datasets (`brain/*.json` + environment/dependency
  inputs) each paired with a manually-written **ideal verdict, expected risk factors, and
  ideal remediation plan**.
- **Quantitative metrics**: verdict-classification **accuracy** + **macro-F1** across the
  4 verdict classes; **risk-factor recall/precision → F1**; remediation **completeness**.
- **Automated evaluation**: an **LLM-as-judge** (the configured `LLMProvider`, structured
  output) scores the generated narrative/remediation against the golden ideal on
  faithfulness, completeness, and actionability. Runs locally — `LocalLLMProvider` for a
  real model judge, or `RuleBasedProvider` (keyword/semantic match) for a fully
  offline/CI run. No external calls required.
- Hypothesis property tests are **kept in addition**, for scoring invariants (e.g. score
  ∈ [0,1]; weight redistribution preserves normalization).

## Consequences
- Gives real, repeatable metrics on AI output quality — not just invariant checks.
- Golden dataset doubles as regression fixtures and demo material.
- LLM-as-judge runs offline (local), not in the assessment hot path; with
  `RuleBasedProvider` it has zero hardware/model cost for CI.

## Implementation note

2026-06-23 — Structural judge and eval report built.

- `tests/eval/judge.py` — `StructuralJudge` + `JudgeResult` dataclasses. Checks
  narrative completeness, classification presence, confidence validity, rationale
  presence, and ideal risk-factor coverage across all 5 golden fixtures.
- `tests/eval/report.py` — `EvalReportRenderer` produces a Markdown report combining
  deterministic metrics (EvalReport) and structural quality (JudgeResult).
- `tests/eval/run_eval.py` — extended: `run_full_eval()` runs both layers in a single
  pipeline pass; `__main__` now emits `docs/eval-report.md`.
- `tests/eval/test_eval.py` — 21 new tests (judge + renderer) added on top of
  existing 13; `FullEvalOutput` fixture runs the pipeline exactly once per module.
- Structural scores: all 5 fixtures achieve 1.00 (all fields present, RuleBasedProvider
  populates every LLM-written field). Prose quality scoring deferred to Phase 2
  (live LLM required).
- `docs/eval-report.md` generated and version-controlled.

2026-06-26 — Prose-quality LLM judge built (FR-28 fully closed).

- `tests/eval/judge.py` — `ProseQualityResponse(RRRModel)` (clarity, specificity,
  actionability, evidence-grounding, overall — each validated 0–1 by Pydantic) +
  `ProseQualityResult` dataclass + `ProseQualityJudge` class. Scores each available
  dimension narrative and the verdict rationale using `ClaudeProvider`
  (`claude-haiku-4-5-20251001`, temperature 0). `is_available()` guard skips scoring
  when `ANTHROPIC_API_KEY` is absent — CI stays green without an API key.
- `tests/eval/run_eval.py` — `run_full_eval()` now returns a 3-tuple
  `(EvalReport, list[JudgeResult], list[ProseQualityResult] | None)`; `run_prose_eval()`
  helper added; `print_report()` updated; `__main__` passes prose results to renderer.
- `tests/eval/report.py` — new §4 Prose Quality table; §4/§5 renumbered to §5/§6;
  gate entry added (informational, threshold ≥ 0.70); methodology note updated.
- `tests/eval/test_eval.py` — 18 new tests: `ProseQualityResponse` bounds validation,
  `is_available()` without key, `judge()` with mocked `ClaudeProvider`, graceful
  failure on `ProviderValidationError`, report renderer with and without prose results.
