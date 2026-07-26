# ADR 0011: Dimension Weight Split

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
The verdict score is a weighted sum of the five dimension scores (FR-7), with the weights
required to sum to 1.0 (FR-15). The split was an open question in the roadmap. The weights
encode a judgment about which dimensions most predict a safe, complete release GO/NO-GO —
they are not all equally predictive.

## Decision
Adopt a **quality & delivery weighted** split:

| Dimension | Weight | Why |
|-----------|--------|-----|
| Test Readiness | 0.30 | Most direct release-safety signal (defect trend, E2E pass rate ≈ production-incident risk) |
| Scope | 0.25 | "Did we deliver what we promised?" — core to release meaning |
| Environment | 0.20 | Deployment readiness; can't ship if envs aren't validated |
| Dependency | 0.15 | External blockers can sink a release regardless of internal readiness |
| Estimation | 0.10 | A program-*predictability* signal, not a release-*safety* one — weakest GO/NO-GO predictor |

Set as the defaults in `src/rrr/config/default_config.yaml`. Weights remain config-overridable;
`ConfigLoader` rejects any override that does not sum to 1.0 (FR-15).

## Consequences
- The verdict reflects release **safety and completeness** first, predictability last.
- Weights stay tunable per program without code changes; the sum-to-1.0 invariant is enforced.
- Estimation can degrade without dominating the verdict — aligns with treating it as a trend/governance signal.

## Alternatives Considered
- **Equal weighting (0.20 each)** — neutral and simple, but rates estimation predictability as
  equally important as test quality, which most release managers would reject.
- **Deployment-gate weighted** — emphasizes environment + dependency as near-vetoes via high
  weights. Rejected because a weighted sum conflates "hard blocker" with "contributor."
- **True veto gates** for Environment/Dependency (missing critical input → NO_GO regardless of
  score) — a stronger model but a larger change to the FR-7/FR-8 weighted-sum design. Deferred;
  revisit in a future ADR if weighted contribution proves insufficient.
