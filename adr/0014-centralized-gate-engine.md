# ADR 0014: Centralized, Config-Driven Gate Engine

- **Status:** Accepted (implemented 2026-06-18)
- **Date:** 2026-06-16

## Context
ADR-0013 specified verdict veto/cap gates that are **individually disable-able with thresholds in
`default_config.yaml → gates`**. The M3 implementation instead realizes gates implicitly: each
assessor emits risk factors whose **severity** is mapped at the orchestrator
(CRITICAL→NO_GO, MAJOR→CONDITIONAL). This drifted from the decision in three ways:

1. The `gates:` config block (per-gate caps, `enabled` flags, thresholds) is **decorative** — you
   cannot disable or retune a single gate without editing assessor code.
2. Gate policy is **scattered** across five assessors instead of centralized.
3. Any *new* MAJOR/CRITICAL risk anywhere **silently shifts verdicts**, and the cap is traceable
   only to a severity, not to a *named* gate.

## Decision
Introduce a single **`GateEngine`** that owns verdict capping:
- Assessors emit **named, typed gate signals** (e.g. `e2e_below_floor`, `blocker_defect`,
  `scope_creep`, `dependency_failed`) on the `DimensionResult`, alongside the human-readable risk
  factor — they detect conditions, they do **not** decide caps.
- The engine reads the `gates:` config (cap level + `enabled` + threshold per named gate) and
  applies the most-restrictive triggered cap, exactly as ADR-0013 describes. The config block
  becomes **load-bearing**.
- Each triggered gate is recorded **by name** in the audit trail (`gates_triggered`).

## Consequences
- Gates are individually tunable and disable-able per program, without code changes (ADR-0013 intent
  honored).
- Verdict caps are explicitly traceable to a named gate, not inferred from severity.
- Adding a risk factor no longer silently changes the verdict — only a registered gate does.
- Requires a small refactor: assessors emit gate signals; the severity→cap logic moves out of
  `verdict.triggered_caps` into the engine. Risk-factor severity remains for human reporting.

## Alternatives Considered
- **Keep the severity-mapping (status quo)** — rejected: not config-driven, scattered, silent.
- **Per-assessor gate config** — rejected: still scatters policy; no single place to reason about
  the gate set.

## Implementation Note (2026-06-17)
Design accepted. `GateEngine` interface: `apply(risk_factors: list[RiskFactor], gate_config: GatesConfig) → Verdict | None` — reads named gates from config, returns the most-restrictive triggered cap or `None`. Assessors will emit a `gate: str | None` field on `RiskFactor` identifying the named gate they signal. `verdict.py` will delegate to `GateEngine` instead of the current severity-mapping inline. Scheduled for M3-hardening sprint.

## Implementation Note (2026-06-18)
Built. `RiskFactor.gate: str | None` replaces the old `bool` field. `GateEngine.apply()` looks up each named gate in `GatesConfig` via `getattr`; if the field is a `Verdict`, uses it as the cap; otherwise falls back to severity (`CRITICAL→NO_GO`, `MAJOR→CONDITIONAL`). This keeps pre-ADR-0014 risk factors working without modification while making named gates config-driven. Five assessors now emit gate names: `environment_down`, `environment_degraded` (environment), `dependency_failed`, `dependency_blocking` (dependency), `blocker_defects` (test_readiness); scope_creep uses severity fallback because `scope_creep_threshold` is a float, not a Verdict. `verdict.triggered_caps` delegates entirely to `GateEngine`. 12 new unit tests in `tests/unit/test_gate_engine.py`. Full 156-test suite green.
