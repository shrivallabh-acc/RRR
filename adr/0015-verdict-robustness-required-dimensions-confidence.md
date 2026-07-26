# ADR 0015: Verdict Robustness — Required Dimensions + Confidence-Aware Capping

- **Status:** Accepted (implemented 2026-06-18)
- **Date:** 2026-06-16

## Context
Two loopholes let an untrustworthy verdict look clean:

1. **Fungible weight redistribution (FR-7).** Unavailable dimensions have their weight redistributed
   among the available ones. With `minimum_assessors = 3`, a **GO is reachable while Environment
   *and* Test Readiness are both unavailable** — "we delivered stories and deps integrate" can
   outvote "is it tested / will it run". Not all dimensions are equally safety-relevant, but
   redistribution treats them as interchangeable.
2. **Confidence is computed but ignored.** `calculate_confidence()` produces a per-dimension value,
   but the verdict label and 0–100 score ignore it — a low-confidence GO (degraded reasoning, half
   the tools failed) is indistinguishable from a high-confidence GO.

## Decision
- **Required dimensions:** a config list of dimensions that must be *available* for a GO. If a
  required dimension is unavailable, the verdict cannot be GO — it is capped to CONDITIONAL (or
  INCOMPLETE if below `minimum_assessors`). **Default:** `[test_readiness, environment]`.
- **Confidence-aware capping:** compute an aggregate confidence (mean of available dims); below a
  configurable `confidence_floor`, cap GO→CONDITIONAL. Surface aggregate confidence on the CLI
  verdict line and in the output model. **Default:** `confidence_floor = 0.70`.

## Consequences
- Closes the "missing the safety-critical dimensions but still GO" loophole.
- Degraded / low-confidence runs can no longer masquerade as clean.
- Adds `thresholds.required_dimensions` and `thresholds.confidence_floor` to config; integrates with
  the GateEngine (ADR-0014) as two more caps.
- Verdict remains deterministic and reproducible.

## Alternatives Considered
- **Status quo** — rejected: the loopholes are real and undermine trust.
- **Per-dimension criticality multipliers on the score** — rejected: opaque; a hard "required +
  confidence cap" is easier to explain to a release manager and easier to audit.

## Implementation Note (2026-06-17)
Design accepted with concrete defaults pinned. Config additions: `thresholds.required_dimensions: [test_readiness, environment]` (list, overridable) and `thresholds.confidence_floor: 0.70` (float). Orchestrator change: after weight redistribution, check (a) each required dim is available — if not, apply CONDITIONAL cap; (b) mean confidence of available dims ≥ floor — if not, cap GO→CONDITIONAL. Surface `aggregate_confidence` on `AssessmentOutputModel` and CLI line. Calibrated against g1–g5 golden set (all pass the 0.70 floor; g4 INCOMPLETE is unaffected as it already triggers the existing `minimum_assessors` guard). Scheduled for M3-hardening sprint.

## Implementation Note (2026-06-18)
Built alongside ADR-0014. `ThresholdsConfig` gains `required_dimensions: list[DimensionName]` (default `[test_readiness, environment]`) and `confidence_floor: float` (default `0.70`), both in `default_config.yaml`. `derive_verdict` applies two post-gate caps: (1) if any required dim is absent and verdict would be GO → CONDITIONAL with an auditable reason; (2) if `aggregate_confidence < confidence_floor` and verdict is GO → CONDITIONAL. `AssessmentOutputModel` gains `aggregate_confidence: float | None`; the CLI verdict line shows `CONFIDENCE: XX%` when set. The `derive_verdict` signature gains `aggregate_confidence` as an optional kwarg (default `None`) — all existing call sites remain compatible. Golden fixtures g1–g5 all pass; g1 holds at GO/96 with confidence well above the floor. 8 new tests in `test_orchestration.py` and `test_gate_engine.py`. Full 156-test suite green.
