# Plan: Programme-First Selection — CLI & UI Rework

> **Pick up here next session.** Self-contained — no prior context needed.
> Status: analysis complete, one open question to resolve at session start (Q1 below).
> Outcome: users can filter to their value stream's releases inside the UI.
> ADR-0022 required before coding.

---

## 0. Key Context — Why This Exists

The user runs the RKT Programme Metrics tool for the **OSM (Offer Selection & Management)
value stream** — also written OS&M or "Offer Selection & Management"; all three are the same
entity. `--value-stream OSM` was therefore **correctly named** from the start.
Do **not** rename it to `--dataset` or any neutral label — OSM is a real value stream.

The brain file `brain/OSM-history.json` covers the OSM value stream's report.
The issue is that the RKT HTML report contains releases from **multiple engineering
programmes** within (and adjacent to) OSM: not everything in the file is equally
in-scope for an OSM stakeholder.

---

## 1. Problem Statement

### 1a — Filter was never implemented

`--value-stream OSM` at the CLI / UI level only **names the brain file**.  It does
not filter which releases are loaded.  The brain file contains all 41 releases from
the HTML report, across multiple engineering programmes.

The user's original intent — "show me OSM releases" — was never delivered.

### 1b — Two different things both called "OSM"

In the data, "OSM" appears in two independent places with different release counts:

| Signal | Field | Typical count | What it means |
|--------|-------|---------------|---------------|
| Engineering programme | `release.programme = "OSM"` | ~22 | Built and shipped by the OSM engineering team |
| TOC sub-domain | `toc_value_stream = "Offer Selection & Management"` | 2 | Directly serves the Offer Selection sub-domain (RetirePlus family) |

These are **not the same set**.  An OSM-programme release often serves
*Account Management* or *Education & Advice* business sub-domains
— `programme = "OSM"` but `toc_value_stream ≠ "Offer Selection & Management"`.

### 1c — Unresolved open question (decide at session start)

> **Q1 — Which "OSM" should the filter target?**
>
> **(A) 22 releases — programme filter.**
> "OSM" means the engineering programme that built it.
> Show everything the OSM team ships, regardless of which business sub-domain.
> `release.programme == "OSM"`.
>
> **(B) 2 releases — TOC sub-domain filter.**
> "OSM" means the Offer Selection & Management business sub-domain specifically.
> Show only releases categorised under "Offer Selection & Management" in the TOC.
> `release.toc_value_stream == "Offer Selection & Management"`.
>
> **(C) Both — stacked.**
> Programme filter narrows to OSM-built releases; TOC filter then lets user drill
> into which sub-domain (Account Management, Education & Advice, etc.) within those.
>
> **Recommendation: Option C (stacked).**
> It is the most complete: an OSM stakeholder sees "my team's releases" by default,
> then can further focus on a specific business sub-domain if needed.
> This also keeps the existing TOC grouping work (ADR-0021) fully useful.

---

## 2. The Three-Dimension Selection Model

| Dimension | Term | Example values | Current state | Target state |
|-----------|------|----------------|---------------|--------------|
| **Value stream / dataset** | `--value-stream` | OSM, Retirement-Services | Brain file selector ✅ | Keep as-is |
| **Programme** | `--programme` | OSM, AIMS, ME&Q, EIMS | CLI only (`rrr --programme`) | **Add to UI — filter buttons** |
| **Business VS (sub-domain)** | TOC buttons | Account Management, Education & Advice | UI only, all panels ✅ | Keep; stack with programme filter |

### Selection hierarchy
```
Value stream (brain file — e.g. OSM report)
  └── Programme filter  ← ADD THIS to the UI
        └── TOC sub-domain filter (already built, ADR-0021)
              └── Individual release
```

---

## 3. What Stays the Same

- `--value-stream` name **unchanged** in all three CLIs.
- TOC VS filter buttons in Releases / History / Trends **unchanged**.
- `release.toc_value_stream` field and all ADR-0021 work **unchanged**.
- `--programme` option in `rrr` CLI **unchanged** (already correct).

---

## 4. What Changes

### 4a — `rrr-ui` CLI — remove `--value-stream`, auto-scan `brain/`

**Current:** `rrr-ui --value-stream OSM` is required at startup.
**Target:** `rrr-ui` scans `brain/` for all `*-history.json` files.
- One file found → auto-load it (no user action needed).
- Multiple files found → show a value-stream picker in the UI header
  (dropdown, `ui.select`).

Remove `--value-stream` from `rrr-ui` CLI options.
Keep it as a hidden backward-compat alias for one release cycle, then remove.

**Rationale:** the value stream a user cares about is known at install time
(they configured `configs/osm.yaml`). Repeating it at every `rrr-ui` invocation
is friction. Auto-scan removes that friction.

### 4b — UI — Programme filter row (the core new feature)

Add a "Programme" filter row **above** the existing TOC VS filter in every panel:
Releases, History, and Trends.

```
── Programme ─────────────────────────────────────────────────────────
  [All (41)]  [OSM (22)]  [AIMS (11)]  [ME&Q (4)]  [EIMS (3)]  …

── Value Stream (TOC) ────────────────────────────────────────────────
  ▶ Account Management  (shown: 8 of 8)
  ▶ Education & Advice  (shown: 6 of 8)
  …
```

Clicking `[OSM (22)]` narrows the pool to 22 releases; the TOC panels rebuild
showing only those 22, with accurate counts.  Clicking a TOC VS button then
further narrows within that programme.  This is **stacked filtering** (Option C).

### 4c — UI header — value-stream identity label

The current header shows `Stream: OSM` (confusing after ADR-0021).
Replace with a label that distinguishes the two axes:

```
Dataset: OSM  ·  Programme: All           ← when no filter active
Dataset: OSM  ·  Programme: OSM (22)      ← when OSM programme filter active
```

Or, with multi-dataset support (if multiple brain files exist), show the dataset
picker in the header and a separate programme label.

---

## 5. Implementation Steps

Work in order.  Run `scripts/check_all.ps1` after Step 3 and after Step 7.

### Step 0 — Write ADR-0022
File: `adr/0022-programme-first-selection-model.md`  
Status: Accepted

**Context** (for the ADR):
`--value-stream` correctly identifies the value stream (e.g. OSM = Offer Selection &
Management).  The gap is that (1) the RKT HTML report includes releases from multiple
engineering programmes, so a UI programme filter is needed to let stakeholders focus on
their team's releases; (2) `rrr-ui` requires `--value-stream` at startup even though
the value stream is already known from the brain file configuration.

**Decision:**
- Add a Programme filter row to Releases, History, and Trends panels.
- Make `rrr-ui` auto-scan `brain/` (remove `--value-stream` CLI flag from `rrr-ui`).
- Keep `--value-stream` unchanged in `rrr` CLI and `rrr-ingest` CLI.

Update `adr/CLAUDE.md` count → 22.  Run `check_alignment.py`.

---

### Step 1 — `rrr-ui/_cli.py` — remove `--value-stream`, delegate to auto-scan

```python
# Remove this option:
@click.option("--value-stream", default=None, help="Override the brain value stream from config.")

# Keep hidden alias for backward compat:
@click.option("--value-stream", "ignored_vs", default=None, hidden=True, expose_value=False)

# run_ui call:
run_ui(config, host=host, port=port, show=not no_browser)
```

Update `run_ui()` signature in `app.py`: remove `value_stream: str | None` parameter.

---

### Step 2 — `app.py` — new helper `list_datasets()`

```python
def list_datasets(config: RRRConfig) -> list[str]:
    """Return sorted dataset labels found in brain/*.json files.

    A label is the stem of <label>-history.json.  Returns an empty list when
    the brain directory is absent or contains no history files.
    """
    brain_dir = Path(config.sources.brain.dir)
    if not brain_dir.exists():
        return []
    return sorted(
        p.stem.removesuffix("-history")
        for p in brain_dir.glob("*-history.json")
    )
```

Tests: `test_list_datasets_returns_stems`, `test_list_datasets_empty_when_no_brain_dir`.

---

### Step 3 — `app.py` — update `register_pages()` and `run_ui()`

Remove `value_stream` parameter from both functions.  Inside `register_pages()`:

```python
datasets = list_datasets(config)
active_dataset = datasets[0] if datasets else config.sources.brain.value_stream
```

Header: if `len(datasets) > 1`, show `ui.select(datasets, …)` picker; else static label.

Make each panel section a `@ui.refreshable` function so the dataset picker can
trigger a panel rebuild without a full page reload:

```python
@ui.refreshable
def releases_section(ds: str) -> None:
    _releases_panel(config, ds)

@ui.refreshable
def history_section(ds: str) -> None:
    _history_panel(config, ds)

@ui.refreshable
def trends_section(ds: str) -> None:
    _trends_panel(config, ds)
```

Dataset picker `on_change`:
```python
on_change=lambda e: (
    releases_section.refresh(e.value),
    history_section.refresh(e.value),
    trends_section.refresh(e.value),
)
```

---

### Step 4 — `app.py` — new helper `list_programmes()`

```python
def list_programmes(releases: list[ReleaseRecord]) -> list[str]:
    """Return sorted unique programme codes present in a release list.

    An empty list means all releases have programme=None — the filter row
    is hidden when there is nothing meaningful to filter.
    """
    return sorted({r.programme for r in releases if r.programme})
```

Tests: `test_list_programmes_returns_sorted_unique`, `test_list_programmes_empty_when_all_none`.

---

### Step 5 — `app.py` — add Programme filter to `_releases_panel()`

Pattern (replicate in History and Trends panels in Step 6):

```python
def _releases_panel(config: RRRConfig, value_stream: str) -> None:
    all_releases = load_releases(config, value_stream)
    programmes = list_programmes(all_releases)

    # Mutable state for the stacked filter.
    current_pool: dict[str, list[ReleaseRecord]] = {"releases": all_releases}

    def _apply_toc_filter(releases: list[ReleaseRecord]) -> None:
        """Rebuild TOC VS groups and render from the given (programme-filtered) pool."""
        grouped = _build_toc_groups(releases)
        # ... (existing TOC render logic, refactored to accept releases arg)

    def _apply_programme_filter(releases: list[ReleaseRecord]) -> None:
        """Narrow to a programme slice, then rebuild TOC groups."""
        current_pool["releases"] = releases
        _apply_toc_filter(releases)

    # Programme filter row — shown only when multiple programmes exist.
    if len(programmes) > 1:
        prog_groups: dict[str, list[ReleaseRecord]] = {"All": all_releases}
        for r in all_releases:
            prog_groups.setdefault(r.programme or "Unknown", []).append(r)

        ui.label("Programme:").classes(
            "text-xs text-gray-500 font-medium uppercase tracking-wide mb-1"
        )
        with ui.row().classes("gap-2 flex-wrap mb-3"):
            for prog in ["All"] + programmes:
                count = len(prog_groups[prog])
                color = "teal" if prog != "All" else "blue-grey"
                ui.button(
                    f"{prog}  ({count})",
                    color=color,
                    on_click=lambda p=prog: _apply_programme_filter(prog_groups[p]),
                ).props("outline").classes("text-xs")

    # TOC VS filter row (existing, unchanged — but now operates on current_pool).
    _apply_toc_filter(all_releases)
```

**Key refactor:** extract `_build_toc_groups(releases)` as a standalone helper
(currently inlined in each panel) so both the programme filter and the TOC VS
filter can call it with different inputs.

---

### Step 6 — Replicate programme filter in `_history_panel()` and `_trends_panel()`

Same pattern as Step 5.  In History, the programme filter narrows `hist_groups`.
In Trends, it narrows the release picker and TOC VS selector.

For History: `vs_lookup` (the `{ir_name: toc_value_stream}` dict) must be built
from the **full** release list (not the programme-filtered one) so cross-references
remain intact even when the filter is active.

---

### Step 7 — Config: update `rrr-ui` docs, remove `--value-stream` from help

Update `src/rrr/ui/_cli.py` module docstring:
```
# Before
rrr-ui [--config PATH] [--value-stream NAME] [--port N] [--host HOST]

# After
rrr-ui [--config PATH] [--port N] [--host HOST]
```

---

### Step 8 — Tests

| File | Change |
|------|--------|
| `tests/unit/test_ui.py` | `list_datasets()` — 2 new tests |
| `tests/unit/test_ui.py` | `list_programmes()` — 2 new tests |
| `tests/unit/test_ui.py` | `run_ui()` signature — remove `value_stream` param |
| `tests/unit/test_ui.py` | Programme filter render — assert buttons appear when >1 programme |

No changes needed to `test_cli.py` or `test_ingest.py` — `--value-stream` unchanged
in `rrr` and `rrr-ingest`.

---

### Step 9 — Artifact sweep (EOD after this session)

| File | Update |
|------|--------|
| `CLAUDE.md` | Commands block: `rrr-ui` usage (remove `--value-stream`); test count |
| `README.md` | Status block; Getting Started code block |
| `README-1.md` | CLI examples |
| `docs/roadmap.md` | ADR-0022 checkbox in M5 |
| `docs/architecture.md` | If CLI section mentions `rrr-ui --value-stream` |
| `docs/ai-usage.md` | Stage entry for this session |
| `.claude/artifact-manifest.md` | ADR count 21→22; ▶ Next action |
| `adr/CLAUDE.md` | Count 21→22 |
| `memory/project-state.md` | ADR count, ▶ NEXT ACTION, Built paragraph |

---

## 6. ADR-0022 Template

```markdown
# ADR-0022: Programme-First Selection Model

Status: Accepted (implemented YYYY-MM-DD)

## Context

The RKT HTML report covers the OSM (Offer Selection & Management) value stream.
Within that report, releases are built by multiple engineering programmes (OSM, AIMS,
ME&Q, EIMS, etc.).  Before this ADR, the UI offered no way to filter releases by
engineering programme — a stakeholder who cares only about OSM-built releases saw
all 41 releases in every panel.

Two further issues: (1) rrr-ui required `--value-stream OSM` at every startup even
though the value stream is already encoded in the brain file path; (2) the programme
filter (`--programme`) already existed in the `rrr` CLI but not in the UI.

## Decision

1. Add a Programme filter row to the Releases, History, and Trends panels in rrr-ui.
   Programmes are derived from `ReleaseRecord.programme`.  The filter stacks above the
   existing TOC sub-domain filter so both dimensions are independently navigable.

2. Remove `--value-stream` from the `rrr-ui` CLI entry point.  The UI auto-scans
   brain/ at startup and loads the only file found, or shows a dataset picker in the
   header when multiple files exist.

3. `--value-stream` is unchanged in `rrr` (assessment) and `rrr-ingest` CLIs — it
   correctly identifies the value stream and determines the brain file path.

## Consequences

Enables:
- Stakeholders can filter to their engineering programme's releases in one click.
- `rrr-ui` starts with no required arguments.

Forecloses:
- Old `rrr-ui --value-stream OSM` invocations will show a deprecation warning from
  the hidden alias; remove the alias in the release after next.

Relation to other ADRs:
- ADR-0021 introduced the TOC sub-domain filter; this ADR adds the programme filter
  above it in the selection hierarchy.
- ADR-0020 defines the NiceGUI dashboard structure; the UI changes are additive.
```

---

## 7. Acceptance Criteria

- [ ] `rrr-ui` starts with no CLI args and auto-loads the brain file
- [ ] When >1 brain file exists, a dataset picker appears in the UI header
- [ ] Programme filter buttons appear in Releases, History, and Trends panels when >1 programme present
- [ ] Clicking `[OSM (22)]` narrows all panels to 22 OSM-programme releases
- [ ] TOC VS filter then applies within that programme-filtered set
- [ ] `pytest` green; `check_comments.py`, `ruff`, `mypy`, `check_alignment.py` all pass
- [ ] ADR-0022 written and accepted; `adr/CLAUDE.md` count = 22

---

## 8. Open Questions

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| Q1 | Which "OSM" filter matters most to the user? | (A) `programme="OSM"` ~22 releases; (B) `toc_value_stream="Offer Selection & Management"` 2 releases; (C) Stacked — both | **C — stacked** |
| Q2 | Config field `brain.value_stream` — rename to `brain.dataset`? | (A) Rename now; (B) Defer | **B — defer; it IS a value stream field, so "value_stream" is correct** |
| Q3 | Should `rrr-ingest` filter to a specific programme during ingest? | (A) Yes — filter at write time; (B) No — keep all, filter at display | **B — keep all in brain for completeness** |

---

*Created 2026-06-29 (revised: OSM is correctly a value stream, not a programme code; rename recommendation withdrawn).
Pick up with `/sod` then: Q1 confirm → ADR-0022 → Steps 1–7 → tests → docs.*
