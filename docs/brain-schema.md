# Brain Input Contract — `<value-stream>-history.json`

> **Status: Accepted** — see [adr/0012-brain-input-contract.md](../adr/0012-brain-input-contract.md).
> This is the normalized contract RRR consumes via the **`RKTBrainReader`** tool. It is a
> pre-aggregated extract of the upstream **RKT Program Metrics** report
> (`docs/RKT Program Metrics Report - *.html`, where the data lives in the embedded
> `__REPORT__` JSON). The HTML→brain extraction is the anti-corruption boundary; assessors
> only ever see this contract, never the raw report.

## File layout
- One file **per value stream**, named `<value-stream>-history.json` (e.g. `Retirement-Services-history.json`),
  located under `brain_dir` (default `./brain`).
- Each file holds **timestamped snapshots** — one per weekly cycle. `RKTBrainReader` selects the
  **latest** snapshot by default, or a specific `date` on request (config: `sources.brain.snapshot`).
- Each snapshot contains a `releases[]` array. One **release** (`ir_name`) is the subject of one
  RRR assessment.

```json
{
  "value_stream": "Retirement-Services",
  "snapshots": [
    {
      "date": "2026-05-28",
      "releases": [
        {
          "ir_name": "Launch 35 - Distribution Modernization",
          "summary":        { "total": 240, "closed": 198, "remaining": 42, "pct": 82.5 },
          "weekly_last3":   [ { "week": "2026-05-12", "value": 18 },
                              { "week": "2026-05-19", "value": 22 },
                              { "week": "2026-05-26", "value": 15 } ],
          "defects_open":   { "total": 12, "by_severity": { "blocker": 0, "critical": 2, "major": 5, "minor": 5 } },
          "defects_closed_cumulative": 87,
          "defect_trend_last5": [ 14, 13, 15, 12, 12 ],
          "sq_avg": 2.4,
          "sq_below_1": [ "repo-legacy-adapter", "repo-batch-processor" ],
          "pv_latest":      { "planned": 200, "actual": 185 },
          "e2e_latest":     { "passed": 142, "failed": 8, "planned": 160 }
        }
      ]
    }
  ]
}
```

## Field → dimension mapping & scoring

| Field | Feeds | Derivation (deterministic score) |
|-------|-------|----------------------------------|
| `summary {total, closed, remaining, pct}` | **Scope** (FR-1) | completion = `closed / total`; classify the release **Delivered ≥0.90 / Partially ≥0.50 / Not <0.50**; score = completion ratio. |
| `weekly_last3[]` | **Scope** context | velocity trend for the narrative; not part of the numeric score. |
| `pv_latest {planned, actual}` | **Estimation** (FR-2) | variance% = `((actual − planned)/planned)×100`; classify over / under / within-tolerance (±10%); score = `max(0, 100 − \|variance%\|)/100`. The extract pre-reduces PV to the latest point, so MAPE = \|variance\| of that point. |
| `sq_avg` (0–3), `sq_below_1[]` | **Test: Quality** (0.4) | sub-score = `sq_avg / 3`; `sq_below_1` repos are flagged as quality risks. |
| `defect_trend_last5[]`, `defects_open.by_severity` | **Test: Defect trend** (0.3) | direction of last-5: declining → **1.0 (improving)**, flat → **0.5 (stable)**, rising → **0.0 (worsening)**; `blocker`/`critical` open counts surface as risk factors. |
| `e2e_latest {passed, failed, planned}` | **Test: E2E** (0.3) | sub-score = `passed / (passed + failed)`. Coverage caveat: `(passed+failed) < planned` means unrun tests — surfaced in evidence. |

**Scope creep (FR-1, gate input):** detected from the **snapshot history** — `summary.total`
(planned SP) growth from the earliest available snapshot (baseline) to the latest. If
`(latest_total − baseline_total)/baseline_total > scope_creep_threshold` (default 0.10), raise a
scope-creep risk factor; this trips the CONDITIONAL gate (ADR-0013). `RKTBrainReader` exposes the
snapshot history so the Scope assessor can compute this without extra inputs.

**Test Readiness composite** = `0.4·quality + 0.3·defect_trend + 0.3·e2e`.
**E2E-absent fallback (ADR-0012):** when `e2e_latest` is null/missing, drop the E2E sub-component
and renormalize the remaining weights (Quality 0.4 / Defect 0.3 → **0.571 / 0.429**), capping
confidence (≤0.5). Quality- and defect-only releases are scored honestly, not penalized to 0.

> **Note — Environment & Dependency are NOT in the brain extract.** They come from separate
> local files / `127.0.0.1` APIs (FR-3 / FR-5), as designed.

## Validation & degradation
- All fields validated by Pydantic v2 at ingest (ADR-0004). A malformed/absent field fails **only
  its dimension**; the run degrades gracefully (ADR-0005) and the verdict stands if
  ≥ `minimum_assessors` succeed.
- `RKTBrainReader` raises a clear error if the requested `value_stream` file, `date` snapshot, or
  `ir_name` release is not found.

## Seam to confirm with the RKT team
- Who owns the **HTML report → brain extract** step (upstream RKT, or an RRR ingest tool)? The
  brain contract above is stable regardless; this only affects where the extractor lives.
- Exact rounding/units of `summary.pct` vs `closed/total` (we compute from `closed/total`).
- Whether `e2e_latest` will be populated for all releases over time (currently sparse upstream).
