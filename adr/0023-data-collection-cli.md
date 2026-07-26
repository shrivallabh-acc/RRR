# ADR-0023: Data Collection CLI — `rrr-collect` and `rrr-ui` Collect Screen

- **Status:** Accepted
- **Date:** 2026-07-04

## Context

RRR requires up to 19 dimension-specific JSON files in `data/` before an assessment run.
Until now, these files are authored manually by release managers and engineers — a process that
is error-prone, inconsistent across teams, and entirely undiscoverable without reading the source.

The problem has three dimensions:

1. **Human ergonomics.** Non-technical release managers should not need to hand-edit JSON.
   They need a guided workflow — either a CLI questionnaire or a UI form.

2. **Automation surface.** Many dimensions (Security, Performance, Accessibility,
   Dependency Risk, Architecture Fitness) can be populated automatically from existing
   CI/CD tool outputs. Without a collector layer, each team invents its own export scripts.

3. **Freshness enforcement.** There is no current mechanism to detect stale or missing data
   files before `rrr` runs. Assessors silently treat missing files as UNAVAILABLE rather
   than alerting the user ahead of time.

## Decision

Introduce a three-layer data collection system sharing a single business logic core:

```
rrr-collect CLI  ─┐
                   ├──▶  CollectorRunner  ──▶  BaseCollector.collect()  ──▶  data/*.json
rrr-ui Collect   ─┘
```

### Layer 1 — `CollectorRunner` (shared business logic, Phase 1)

`src/rrr/collectors/runner.py` — framework-agnostic Python. Responsibilities:
- `status(release, data_dir, tier)` — scan `data/` for missing/stale files and return
  a per-dimension `CollectorStatus` (fresh / stale / missing) based on `captured_at`.
- `run(dimension, release, collector, data_dir)` — call `collector.collect()`, validate
  the result against the dimension's `InputContract`, write `data/<dimension>.json`.
- Called identically from the CLI and from the NiceGUI Collect screen.

### Layer 2 — `BaseCollector` ABC and collector implementations (Phase 1/2)

`src/rrr/collectors/base.py`:
```python
class BaseCollector(ABC):
    @property
    @abstractmethod
    def dimension(self) -> str: ...          # matches DimensionName value

    @abstractmethod
    def collect(self, release: str, config: CollectorConfig) -> dict[str, Any]: ...
```

**Phase 1 — `InteractiveCollector`** (`src/rrr/collectors/interactive.py`):
Introspects the dimension's Pydantic `InputContract` model to generate Click prompts
automatically. Enum fields → `click.Choice`; bool → `click.confirm`; int/float →
`click.prompt` with type; list → repeated prompts. Loads the existing file first
(update mode — shows current values as defaults). Supports `--skip-optional` to accept
defaults for non-CRITICAL fields. No external dependencies.

**Phase 2 — Tool adapters** (`src/rrr/collectors/adapters/`):
Each adapter implements `collect()` by calling an external tool API or parsing a CI
artifact. Returns a partial dict covering only the fields it can populate. The runner
merges adapter output with interactive prompts for remaining fields. All adapters must
enforce the ADR-0010 host allow-list — no call to a non-allow-listed host is permitted.

Initial adapter set: `sonarqube`, `snyk`, `k6`, `axe`, `lighthouse`, `grafana`,
`datadog`, `terraform`, `github_actions`, `snyk_sca`, `owasp_dep_check`.

### Layer 3 — Presentation surfaces

**`rrr-collect` CLI** (`src/rrr/collectors/_cli.py`, new entry point):
```
rrr-collect [--release NAME] [--tier hotfix|standard|major]
            [--dimension DIM] [--all] [--status]
            [--adapter ADAPTER] [--refresh] [--skip-optional]
            [--data-dir DIR]
```
- `--status` — print per-dimension traffic-light (fresh / stale / missing), exit.
- `--all` — collect all dimensions required for the given tier (uses `TierThresholds.required_gate_dims`).
- `--adapter NAME` — use a named tool adapter instead of interactive prompts.
- `--refresh` — overwrite even if file is fresh.

**`rrr-ui` Collect screen** (extends ADR-0020):
New "Collect" nav item in the left sidebar. Layout:
- **Status panel** — per-dimension traffic-light row for the selected release and tier.
- **Dimension form page** — clicking a dimension opens a NiceGUI form driven by the
  same `InputContract` schema. Field types map: enum → `ui.select`; bool → `ui.switch`;
  int/float → `ui.number`; list → `ui.chip` tag input. Save calls `CollectorRunner.run()`.

## Consequences

**Enables:**
- Release managers can collect all data via CLI or browser without editing JSON.
- CI/CD pipelines can auto-populate tool-generated dimensions on every build.
- Pre-flight status check (`rrr-collect --status`) surfaces missing/stale data before
  `rrr` runs, replacing silent UNAVAILABLE verdicts.
- New assessors (M6) gain collection support automatically: adding a dimension's
  `InputContract` model is sufficient for `InteractiveCollector` to generate its prompts.

**Constraints:**
- Adapter layer introduces outbound network calls. Every adapter MUST check the
  ADR-0010 host allow-list before each request — identical enforcement as `ApiSource`.
- Adapter credentials (API tokens) MUST be read from environment variables only —
  never from config files. The `CollectorConfig` carries env-var names, not values.
- `CollectorRunner` MUST NOT make network calls — that is the adapter's job. The runner
  is always safe to call offline.
- The `rrr-ui` Collect screen writes to `data/` on the server's local filesystem.
  In a hosted deployment this means the `data/` path must be volume-mounted.

## Implementation note

**2026-07-09 — Phase 1 (CollectorRunner + InteractiveCollector + rrr-collect CLI) built:**
`src/rrr/collectors/` package added with five modules:
- `base.py`: `BaseCollector` ABC, `CollectorConfig` dataclass, `CollectorResult` dataclass.
- `runner.py`: `CollectorStatus` enum (FRESH/STALE/MISSING); `DimensionStatusReport` dataclass;
  `CollectorRunner` with `status()` (scan `data/` for freshness) and `run()` (validate + write).
- `registry.py`: `CollectorRegistry` mapping 14 supplementary dimensions to their `InputContract`
  classes. Brain-backed dimensions (scope, estimation, test_readiness, dependency) excluded —
  those come from `brain/*.json` via `rrr-ingest`.
- `interactive.py`: `InteractiveCollector` — introspects `model_class.model_fields` to generate
  Click prompts. Enum → `Choice`; bool → `confirm`; int/float/str → typed prompt; dict/list → skip
  with advisory. Uses `field_info.is_required()` (Pydantic v2 API) rather than `PydanticUndefined`.
  Loads existing file values as prompt defaults (update mode).
- `_cli.py`: `rrr-collect` Click command. `--status` exits 0 (all FRESH) or 2 (any stale/missing).
  `--dimension` collects one dimension (skips if FRESH unless `--refresh`). `--all` collects all
  active dims for the tier. `--tier hotfix` excludes accessibility + architecture dimensions.
`pyproject.toml` wired: `rrr-collect = "rrr.collectors._cli:cli"`. 32 new tests in
`tests/unit/test_collectors.py`. Full quality gate green: comments (80 files), ruff, mypy (93 files).

**2026-07-10 — Phase 2 (rrr-ui Collect screen) built:**
`_collect_panel()` added to `src/rrr/ui/app.py`; "Collect" nav item added to the
sidebar (admin section, beside "Ingest"). Status/form sub-view pattern: the inner
`ui.column()` toggles between a freshness status grid and an InputContract-driven
form without a full page reload. Form field dispatch: Enum → `ui.select`, bool →
`ui.switch`, int/float → `ui.number`, str → `ui.input`; dict/list → advisory note.
Save uses `_DictCollector(BaseCollector)` + `CollectorRunner.run()` so all validation
and file-write logic remains in the shared runner. Pure-Python helpers:
`collect_status_all()` (wraps `CollectorRegistry` + `CollectorRunner.status()`) and
`load_collect_form_data()` (reads existing JSON for update-mode pre-population).
Supporting type-dispatch helpers: `_unwrap_collect_optional()`, `_build_collect_field_widget()`.
6 new unit tests in `tests/unit/test_ui.py`; full quality gate green.

Phase 2 items remaining: tool adapters (snyk, sonarqube, k6, axe, etc.).

## Alternatives considered

- **Extend `rrr-ingest`** — rejected: `rrr-ingest` is purpose-built for brain data (HTML → JSON).
  Mixing it with supplementary dimension collection conflates two unrelated concerns.
- **Shell script generator** — rejected: per-team drift, no validation, no UI path.
- **Form-only (no CLI)** — rejected: CI/CD automation requires a scriptable interface.
  Both surfaces are needed and they share 100% of the business logic via `CollectorRunner`.
