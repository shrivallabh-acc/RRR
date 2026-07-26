# ADR-0022: Programme-First Selection Model for rrr-ui

**Status:** Accepted (implemented 2026-06-29)

## Context

The `rrr-ui` dashboard was launched with a mandatory `--value-stream` CLI argument that
determined which brain file to load (e.g. `brain/OSM-history.json`).  This was modelled
after the `rrr` CLI, where `--value-stream` is a required parameter.

After smoke-testing the dashboard against 41 real OSM releases (ADR-0020 session), two
problems became clear:

1. **The `--value-stream` argument is redundant when only one brain file exists.**  A
   user who has ingested only `brain/OSM-history.json` should be able to run `rrr-ui`
   without specifying `--value-stream OSM`; the application should discover the file
   automatically.

2. **The programme filter is missing from the UI.**  The `rrr` CLI has `--programme` to
   narrow releases by engineering team code (e.g. `OSM`, `AIMS`, `ME&Q`).  The dashboard
   has no equivalent — all 40+ releases from the brain file are shown without any way
   to focus on a specific team's delivery.

These two things called "value stream" must be distinguished:

| Name | Source field | Example values | What it means |
|------|-------------|----------------|---------------|
| Brain file (dataset) | file name `brain/<name>-history.json` | `OSM` | Which ingested dataset to load |
| TOC value stream | `release.toc_value_stream` (ADR-0021) | `Offer Selection & Management` | Business sub-domain from RKT TOC slide |
| Programme (engineering team) | `release.programme` | `OSM`, `AIMS`, `ME&Q`, `EIMS` | Which engineering team owns the release |

The `--value-stream` argument has always referred to the *dataset* (brain file).  The
name is correct — OSM, OS&M, and Offer Selection & Management are all valid aliases for
the same value stream.  No rename is needed.

## Decision

### 1. rrr-ui CLI: auto-scan brain/ when no `--value-stream` is given

Remove `--value-stream` from the `rrr-ui` CLI.  On start-up, `run_ui()` calls
`list_datasets(config)` which scans `brain/*-history.json` and returns the discovered
dataset labels.  If exactly one file is found, it is used automatically.  If multiple
files are found, a dataset picker appears in the page header.

`list_datasets()` is a pure function in `src/rrr/ui/app.py`.  The `--value-stream`
option is removed from `src/rrr/ui/_cli.py`.

### 2. Dataset picker in rrr-ui header (multiple brain files)

When `list_datasets()` returns more than one label, the page header shows a `ui.select`
dropdown.  Selecting a dataset navigates to `/?dataset=<label>`, which reloads the page
with the new brain file.  The `register_pages()` function accepts a `dataset` query
parameter on the `@ui.page("/")` route.

### 3. Programme filter row in Releases, History, and Trends panels

Each panel gains a **Programme filter row** above the existing TOC VS filter.  When the
panel loads, `list_programmes(releases)` returns all distinct `release.programme` values,
sorted.  One button per programme (plus an "All" button) is shown.

Clicking a programme button narrows the release pool for that panel.  The TOC VS
grouping (Releases panel: expansion panels; History/Trends: filter buttons) rebuilds
from the narrowed pool.  This means programme and TOC VS filters are **stacked** — the
user first picks a team, then drills in by business sub-domain.

`list_programmes(releases)` is a pure function in `src/rrr/ui/app.py`.

### 4. rrr and rrr-ingest CLIs: unchanged

`rrr --value-stream <name>` and `rrr-ingest --value-stream <name>` keep their existing
`--value-stream` option.  No changes are made to these CLIs.

## Consequences

**Enables:**
- Zero-argument `rrr-ui` start for the common single-dataset case.
- Focused per-team views within a shared brain file (e.g. filter to OSM-programme
  releases within the OSM dataset, independent of the "Offer Selection & Management"
  TOC VS sub-domain).
- Clear separation of three selection dimensions: dataset → programme → TOC VS.

**Forecloses:**
- `rrr-ui --value-stream` as a shorthand to pre-select the dataset.  Users with
  multiple brain files must use the in-page picker.

**Risks:**
- If `brain/` is empty on first run, all panels show their empty-state placeholders
  rather than erroring; this is handled by `list_datasets()` returning `[]` and a
  guard in `run_ui()` that falls back to `config.sources.brain.value_stream`.

**Implementation note:** 2026-06-29 — implemented in `src/rrr/ui/app.py` and
`src/rrr/ui/_cli.py`.  `list_datasets()` and `list_programmes()` added as data
helpers.  Programme filter row added to `_releases_panel()`, `_history_panel()`, and
`_trends_panel()`.  Dataset picker added to `register_pages()` header.
`--value-stream` removed from `rrr-ui` CLI.
