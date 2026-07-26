# ADR-0018: HTML Ingest Tool — RKT Report → Brain Contract

- **Status:** Accepted (implemented 2026-06-22)
- **Date:** 2026-06-22

## Context

Three assessors consume `brain/<value-stream>-history.json` via `RKTBrainReader` (ADR-0012).
The source of record is the RKT Program Metrics HTML report, whose machine-readable data lives in
a single embedded JSON literal (`const __REPORT__ = {...}`). Until now, the HTML→brain extraction
step was left as an upstream responsibility. In practice the user owns the HTML files and needs
RRR itself to perform the extraction — keeping the ingest logic inside the project maintains the
anti-corruption boundary and gives assessors a single, stable input contract regardless of how
the HTML schema evolves.

## Decision

1. **New `src/rrr/ingest/` module** with two classes:
   - `HTMLExtractor` — reads one HTML file, extracts `__REPORT__` via regex (never parses the
     HTML DOM), maps each release to the brain contract shape.
   - `BrainWriter` — reads the existing `<value-stream>-history.json` if present, upserts the new
     dated snapshot (idempotent on same date), and writes back. History accumulates across weekly
     runs.

2. **New `rrr-ingest` console-script entry point** (`pyproject.toml`). The existing `rrr` command
   is unchanged; breaking it to a subgroup belongs in the M5 CLI refactor.

   ```
   rrr-ingest --html-dir <path> --brain-dir <path> --value-stream <name>
   ```

3. **Field mapping** from `__REPORT__` to the brain contract (ADR-0012):

   | Brain field | HTML source | Notes |
   |---|---|---|
   | `date` | `generated` | "June 19, 2026 ..." → "2026-06-19" |
   | `ir_name` | `release.ir_name` | Direct |
   | `summary {total,closed,remaining,pct}` | `release.summary` | 4 of 8 fields kept |
   | `weekly_last3` | `release.weekly` | Last 3 `{week,value}` pairs |
   | `pv_latest` | `release.pv.{pv,actual}[-1]` | Last value of each series |
   | `sq_avg` | `mean(sq_caps.scores) × 3` | HTML 0–1 → brain 0–3 scale |
   | `sq_below_1` | `sq_caps` | Names where `score × 3 < 1.0` |
   | `defect_trend_last5` | `defect_trend.{created,resolved}` | Running cumulative open, last 5 |
   | `defects_open` | `defect_priority.{labels,matrix}` | Sum matrix cols by priority label |
   | `defects_closed_cumulative` | `sum(defects_closed.values)` | Running total |
   | `e2e_latest` | `release.e2e_overall[-1]` | Real counts (not %); null if empty |

4. **Value stream name** is user-supplied via `--value-stream`; it is not present in the HTML.
   All 41 releases in one HTML file go into one snapshot under that value stream.

5. **Idempotent upsert**: if a snapshot for the extracted date already exists in the history file,
   it is overwritten (re-running the same HTML is safe). Snapshots for other dates are untouched.

## Consequences

- The user workflow is: drop HTML files in a folder → `rrr-ingest` → `rrr --release "..."`.
- The anti-corruption boundary (ADR-0012) is maintained: assessors never see the HTML shape.
- `sq_avg` stored on the 0–3 scale matches the `RKTBrainReader` Pydantic model and assessor
  arithmetic (`quality = sq_avg / 3`) without any schema change.
- `e2e_latest` uses the per-release `e2e_overall` series (real counts) not `e2e_progress`
  (percentages); releases with no E2E data produce `null`, triggering the E2E-absent fallback
  path (ADR-0012 §3).
- The `rrr-ingest` entry point is a separate script; the existing `rrr` command, all tests, and
  the demo script are unmodified. CLI unification belongs in M5.

## Alternatives Considered

- **`rrr ingest` as a subcommand** — requires converting `main` to a Click group, breaking
  `rrr --release` syntax and all existing tests. Deferred to M5 CLI refactor.
- **Standalone `scripts/ingest_html.py`** — outside the package, not pip-installable, no
  structured logging, no Pydantic validation at the output boundary. Rejected.
- **Assessors read the HTML directly** — binds the domain to a chart-centric, report-versioned
  shape. Explicitly rejected in ADR-0012.
