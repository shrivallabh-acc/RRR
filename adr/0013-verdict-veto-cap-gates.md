# ADR 0013: Verdict Veto / Cap Gates

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
The verdict was a pure weighted sum of dimension scores mapped to bands (FR-7/FR-8, ADR-0011).
That structurally cannot express a **single critical failure blocking a release** regardless of how
strong everything else is — the reality of GO/NO-GO. Concretely, with the ADR-0011 weights, a
release with `test_readiness = 0` but everything else perfect still scores **0.70 → CONDITIONAL**;
NO_GO is unreachable. The evaluation golden set assumes gating: `g2_failing_tests → NO_GO`,
`g5_scope_creep → CONDITIONAL`. A weighted average alone is the wrong shape for those.

## Decision
Keep the weighted score, then apply **veto/cap gates** that ceiling the verdict. The final verdict
is the **most restrictive** of the score band and every triggered cap, on the ordering
**GO (2) > CONDITIONAL (1) > NO_GO (0)**. INCOMPLETE (fewer than `minimum_assessors` succeed) takes
precedence over all (ADR-0005).

```
if successful_dimensions < minimum_assessors:  verdict = INCOMPLETE
else:
    band = GO if score>=0.80 elif score<0.40 NO_GO else CONDITIONAL   # FR-8
    verdict = min(band, *triggered_caps)                              # most restrictive wins
```

Default gates (all thresholds in `default_config.yaml → gates`, and individually disable-able):

| Gate | Condition (default) | Cap |
|------|---------------------|-----|
| E2E critical | E2E pass rate `< e2e_critical_floor` (0.50) | **NO_GO** |
| Blocker defects | `defects_open.by_severity.blocker > 0` | **NO_GO** |
| Critical defects | `defects_open.by_severity.critical > critical_defects_limit` (0) | **CONDITIONAL** |
| Environment down | any component `stability == down` | **NO_GO** |
| Environment degraded/missing | any `stability == degraded` OR `provisioning == missing` | **CONDITIONAL** |
| Dependency failed | any dependency `integration == failed` | **NO_GO** |
| Dependency blocking/at-risk | any `blocking` (not_started) OR `at_risk` dependency | **CONDITIONAL** |
| Scope creep | planned-SP growth across snapshots `> scope_creep_threshold` (0.10) | **CONDITIONAL** |

Each triggered gate is recorded as an explicit **risk factor** in the audit trail, so the cap is
always traceable to its cause. Risk acceptance (FR-7) can later waive a specific gate.

## Consequences
- The realistic "great features, broken tests → block the release" case is now expressible; the
  golden set (g2 NO_GO, g5 CONDITIONAL) is satisfiable.
- Verdict logic is no longer a single monotone function of the score — but it remains
  **deterministic and reproducible** (gates are threshold rules on deterministic inputs).
- Scope-creep detection now has a concrete source: `summary.total` growth across brain snapshots
  (the history `RKTBrainReader` already holds). Reconciles FR-1's "detects scope creep".
- Gates are config-driven and disable-able, so the model can be tuned per program without code
  changes. Determinism property tests (evaluation-plan.md §5) must cover gate outcomes too.

## Alternatives Considered
- **Pure weighted sum (status quo)** — rejected: cannot express critical single-dimension vetoes.
- **Risk-penalty subtraction** (risk factors subtract from the score) — viable and softer, but
  penalty sizes are arbitrary and a large penalty is just a fuzzy gate; hard caps are clearer to
  explain to a release manager ("E2E below 50% → NO_GO") and easier to audit.
- **Change the eval targets to match the weighted model** — rejected: abandons a real release
  scenario the tool should catch.
