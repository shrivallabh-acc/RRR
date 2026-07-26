# ADR-0020: NiceGUI Web Dashboard

**Status:** Accepted (implemented 2026-06-26)

## Context

M5 scale-out requires a human-facing interface beyond the CLI. The three user
needs that drove this decision are:

1. **Browse all releases** from the ingested brain JSON with visual metric bars
   (scope completion, SQ quality, E2E pass rate, open-defect counts) — before
   deciding which release to assess.
2. **Trigger a release assessment** (`pipeline.run_and_record()`) without
   opening a terminal.
3. **Review assessment history** from SQLite with verdict badges and trend
   indicators, and drill into any past result's full verdict card.

A CLI-only interface forces the user to know the exact release name, run a
separate `--list-releases` command, and parse JSON output mentally. A web UI
collapses all three steps into one coherent flow.

### Constraints that shaped the choice

- **Local-first (ADR-0010, NFR-8):** The UI must bind to `127.0.0.1` by
  default and make no external network calls at runtime.
- **Optional, not core:** The dashboard is a convenience layer; the pipeline
  and CLI must work without it. The UI dep must be optional (`pip install
  rrr[ui]`).
- **Python-only stack:** The team operates in a Python-native environment.
  Adding a separate TypeScript/React frontend would require a separate build
  step, a different language, and a dev-server round-trip.
- **Blocking `assess()` call:** The pipeline runs synchronously (~1–2 s with
  `RuleBasedProvider`, ~5–10 s with `ClaudeProvider`). The framework must
  handle async wrapping so the UI stays responsive.

### Options considered

| Option | Pros | Cons |
|--------|------|------|
| **NiceGUI** | Pure Python, single process, async-native, Quasar/Tailwind built-in, `pip install` only | Relatively new framework; smaller community than Flask/FastAPI |
| Flask + Jinja2 | Mature, well-known | No reactive UI; every interaction needs a full page reload or hand-rolled JS |
| FastAPI + React | Best-in-class API layer; rich UI | Two languages, separate build step, adds significant dev complexity |
| Streamlit | Very quick to prototype | Stateless execution model makes async assessment difficult; page-refresh model |

NiceGUI is the right fit: pure Python, event-loop-native (so `asyncio.
run_in_executor` keeps the UI responsive during assessment), and Quasar
components provide polished table/badge/progress-bar primitives without
requiring custom CSS.

## Decision

Introduce a **NiceGUI 2.x web dashboard** as an optional dependency under
`rrr[ui]`:

- **Entry point:** `rrr-ui` CLI command (`src/rrr/ui/_cli.py`), starts the
  NiceGUI server on `127.0.0.1:8080` by default.
- **Pages:** Single tabbed page (`/`) with two panels:
  - **Releases** — reads `brain/<vs>-history.json` via `RKTBrainReader`; card
    per release with scope/SQ/E2E metric bars; "Run Assessment" button.
  - **History** — reads from SQLite via `AssessmentStore.all_recent()`; past
    verdicts with colour-coded chips, scores, and trend indicators.
- **Assessment execution:** `pipeline.run_and_record()` runs in
  `asyncio.get_event_loop().run_in_executor(None, ...)` so the NiceGUI event
  loop is never blocked.
- **Local-first binding:** `ui.run(host="127.0.0.1")` — the server is not
  reachable from other machines unless the user explicitly overrides `--host`.

## Consequences

**Enables:**
- Non-technical stakeholders can browse release metrics and trigger assessments
  without learning the CLI.
- The full release-to-verdict flow becomes a three-click operation.
- `AssessmentStore.all_recent()` is a new store method that future API layers
  can also reuse.

**Forecloses / trade-offs:**
- NiceGUI couples the UI layer to a specific Python web framework; migrating
  later would require a rewrite of `app.py`.
- The dashboard is not a substitute for the CLI in automated pipelines (CI,
  cron jobs) — the CLI remains the canonical interface for scripted use.
- NiceGUI's test-client support requires `nicegui[testing]` (headless browser);
  full UI integration tests are deferred. Data helpers and the store method are
  fully unit-tested.

## Implementation notes

2026-06-26 — `src/rrr/ui/` package created; `rrr-ui` entry point added to
`pyproject.toml`; `AssessmentStore.all_recent()` added; data-helper and
persistence tests added. Optional dep: `pip install rrr[ui]`.

2026-06-29 — Release Detail panel added (M5 roadmap item A): `_releases_panel()`
rewritten as two-pane `ui.splitter()` master-detail layout. Left pane: compact
clickable release cards with scope indicator. Right pane: five-tab detail panel
(Overview / Environment / Dependencies / Security / Assessments). New pure-Python
data helpers `load_environment()`, `load_dependency()`, `load_security_data()`,
`latest_for_release()` added; 10 new unit tests (428 total).

2026-06-29 — UI redesign: `src/rrr/ui/app.py` completely rewritten. Two-pane
splitter and nested tabs replaced with a persistent left sidebar (140 px,
`ui.left_drawer`) + content-area navigation pattern (no full page reloads).
New screens: **Overview** home (4-stat health row + searchable/sortable release
table, urgency-sorted, unassessed rows greyed at bottom); **Release Detail**
single scrollable page (verdict hero with in-place refresh → dimension scorecard
with trend arrows → risk factors → rationale → remediation → source metrics →
environment → dependencies → security → assessment history with drill-in dialog).
Functions added: `_nav_item`, `_stat_card`, `_overall_trend`, `_overview_panel`,
`_release_detail`. Removed: `_releases_panel`, `_release_detail_panel`,
`_detail_overview`, `_detail_assessments`. Full quality gate green; 428 tests.

2026-07-10 — M7 Phase 2 **Collect screen** added (ADR-0023 Phase 2 UI surface):
New "Collect" nav item in sidebar (beside "Ingest" in the admin section).
`_collect_panel()` renders two sub-views sharing an inner `ui.column()`:
(1) **Status view** — per-dimension FRESH/STALE/MISSING badge table via
`collect_status_all()`; Refresh button re-queries without page reload.
(2) **Form view** — `_show_form(dimension)` introspects `InputContract.model_fields`
and renders one NiceGUI widget per non-auto field (Enum→select, bool→switch,
int→number, float→number, str→input). Save routes through `_DictCollector` +
`CollectorRunner.run()` so validation and the write path are shared with the CLI.
New pure-Python helpers `collect_status_all()` and `load_collect_form_data()` are
unit-testable without NiceGUI. Supporting helpers: `_DictCollector(BaseCollector)`,
`_unwrap_collect_optional()`, `_build_collect_field_widget()`. 6 new unit tests
in `tests/unit/test_ui.py`. Full quality gate green.
