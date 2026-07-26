# ADR 0012: Brain Input Contract & RKT Anti-Corruption Boundary

- **Status:** Accepted
- **Date:** 2026-06-08

## Context
Three assessors (Scope, Estimation, Test Readiness) read upstream **RKT Program Metrics** data
(FR-1, FR-2, FR-4). The source of record is the RKT **HTML executive report** (`docs/RKT Program
Metrics Report - *.html`), whose machine-readable data lives in an embedded `__REPORT__` JSON
object (40 releases of earned-value, software-quality, and defect series). That raw shape is
report-centric and chart-oriented — unsuitable for assessors to consume directly. A pre-aggregated,
per-value-stream extract — `brain/*.json`, read by the **`RKTBrainReader`** tool — provides a clean,
stable contract. This ADR fixes that contract and the scoring derivations it implies.

## Decision
1. **Normalized contract = `<value-stream>-history.json`.** One file per value stream, holding
   timestamped weekly `snapshots[]`, each with `releases[]`. `RKTBrainReader` selects the latest
   snapshot by default (or a requested date) and a release by `ir_name`. Full field spec:
   [docs/brain-schema.md](../docs/brain-schema.md).
2. **Anti-corruption boundary.** The raw RKT report (`__REPORT__`) is extracted into the brain
   contract *upstream of the assessors*; assessors and tools consume the brain contract only. The
   report's chart-centric shape never leaks into the domain.
3. **Scoring derivations** (reconciling FR-2/FR-4 to the real fields):
   - **Estimation** — `pv_latest {planned, actual}` (latest earned-value point, not a per-item
     list): variance% = `((actual−planned)/planned)×100`; score = `max(0,100−|variance%|)/100`.
     The prior "≥3 items / 3+ consecutive runs" model does not apply and is dropped.
   - **Test Quality** — `sq_avg/3` (0–3 scale); `sq_below_1` repos flagged.
   - **Defect trend** — direction of `defect_trend_last5` (declining→1.0, flat→0.5, rising→0.0);
     `defects_open.by_severity` blocker/critical surfaced as risk factors.
   - **E2E** — `passed/(passed+failed)` from `e2e_latest`. **When `e2e_latest` is absent, drop the
     E2E sub-component and renormalize Quality/Defect weights (0.4/0.3 → 0.571/0.429) with reduced
     confidence.**
4. **Validate at ingest** (Pydantic v2, ADR-0004); a bad/missing field fails only its dimension and
   degrades gracefully (ADR-0005).

## Consequences
- M1 modeling is unblocked against a confirmed, concrete schema; example fixture exists under
  `tests/golden/`.
- RKT report changes are absorbed at the extraction boundary, not propagated across assessors
  (satisfies the "schema drift" risk in architecture.md).
- Scope is assessed at **release level** (`summary`), not per-capability — the brain extract does
  not carry per-capability story-point breakdowns. FR-1 is reconciled accordingly.
- Estimation rests on a **single latest PV point**; it reflects current planned-vs-actual standing,
  not historical estimation discipline. Acceptable given the available data.
- One open seam remains: ownership of the HTML→brain extraction step (upstream vs. an RRR ingest
  tool). The contract is stable either way.

## Alternatives Considered
- **Assessors parse the RKT HTML/`__REPORT__` directly** — rejected: binds the domain to a
  chart-centric, report-versioned shape; violates the bounded-context discipline.
- **Per-domain files (`scope.json`/`estimation.json`/`test.json`)** — the earlier proposal in this
  ADR; superseded by the actual `RKTBrainReader` contract (value-stream history with snapshots),
  which also gives free historical trend data (FR-9) via prior snapshots.
- **Keep FR-2's per-item MAPE / consecutive-run model** — rejected: the source has no per-item
  estimate list, only a latest earned-value point.
