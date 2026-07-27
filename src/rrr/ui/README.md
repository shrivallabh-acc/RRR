# UI

NiceGUI web dashboard for browsing releases, running assessments, and visualising
trends. Requires `pip install "rrr[ui]"` (ADR-0020).

---

## Module overview

| File | Purpose |
|---|---|
| `app.py` | Full NiceGUI application — all screens and navigation |
| `_cli.py` | `rrr-ui` Click entry point |
| `helpers.py` | Pure-Python data helpers: `collect_status_all()`, `load_collect_form_data()`, `score_history_data()` |

---

## Starting the dashboard

```powershell
pip install -e ".[ui]"

rrr-ui                               # default: http://127.0.0.1:8080
rrr-ui --config configs/osm.yaml     # with a config override
rrr-ui --port 9090                   # different port
rrr-ui --host 0.0.0.0               # bind all interfaces (use with caution)
rrr-ui --no-browser                  # don't open a browser tab
```

---

## Dashboard screens

### Overview

Home screen with programme context:
- 4 summary stat tiles: Total / NO_GO / CONDITIONAL / Unassessed
- Sortable release table (NO_GO first by default)
- Programme selector (auto-detected from brain files)

### Release Detail

Single-scroll detail page for one release:
- Verdict hero banner (GO/NO_GO/CONDITIONAL/INCOMPLETE + score + confidence)
- Dimension scorecard: score bar, trend arrow (↑/→/↓), confidence percentage
- Risk factor table: CRITICAL / MAJOR / MINOR with gate reference
- LLM rationale and remediation text
- Environment data panel
- Dependency status panel
- Security summary (if security dimension configured)
- Assessment history for this release

### History

Cross-release activity feed:
- Programme filter buttons
- TOC value-stream filter buttons
- Each entry shows release name, verdict badge, score, date

### Trends

ECharts score-over-time line chart:
- Release selector (all assessed releases for the programme)
- GO (0.80) and NO_GO (0.40) threshold reference lines
- Per-assessment data points with tooltips

### Collect

Interactive data collection screen mirroring `rrr-collect`:
- FRESH / STALE / MISSING badge per dimension with last-updated timestamp
- Click a dimension → form view with InputContract-driven widgets:
  - `Enum` → `ui.select` dropdown
  - `bool` → `ui.switch`
  - `int`/`float` → `ui.number`
  - `str` → `ui.input`
- Save button writes via `CollectorRunner` (same path as `rrr-collect`)
- Refresh button re-checks status

---

## HTTP Basic Auth

Set credentials in config (never hardcode — use env-var interpolation):

```yaml
ui:
  auth_user: "admin"
  auth_password: "${UI_PASSWORD}"
```

Both fields must be set together or both omitted.

---

## Architecture notes

- `app.py` uses a **persistent left sidebar** (140 px) + content-area navigation.
  There are no nested tabs — navigation is through the sidebar.
- The dashboard auto-scans `brain/` for `*-history.json`. With multiple brain files,
  a dataset picker appears in the header.
- All data helpers in `helpers.py` are pure functions (no NiceGUI imports) for
  testability — 9 unit tests in `tests/unit/test_ui_helpers.py`.
- The NiceGUI server binds to `127.0.0.1` by default (local-first, ADR-0010).
