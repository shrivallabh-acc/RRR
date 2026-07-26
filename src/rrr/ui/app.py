"""NiceGUI web dashboard for RRR — sidebar-navigated release-readiness interface (ADR-0020).

A persistent left sidebar (140 px) leads to four top-level screens.  Navigation is
client-side: clicking a sidebar item clears the content area and renders the new screen
without a full page reload.  The dataset is resolved from the ``?dataset=`` query
parameter on each browser page load; switching datasets does trigger a reload so the
brain data resets cleanly.

Screens
-------
**Overview** (home)
    Programme health summary row (four stat cards: total, NO-GO, CONDITIONAL, not
    assessed) followed by a searchable, filterable, sortable release table.  Rows are
    sorted by urgency — NO-GO → CONDITIONAL → GO → unassessed — then by descending
    score within each group.  Unassessed rows appear greyed at the bottom.  Clicking
    any row navigates to the Release Detail screen without a page reload.

**Release Detail**
    A single scrollable page, not tabs-within-tabs.  Sections from top to bottom:

    1. *Verdict hero* — full-width colour-coded card (GO / NO-GO / CONDITIONAL /
       INCOMPLETE) with large score, confidence, and timestamp.  The ``[Run Assessment]``
       button in the breadcrumb row is the primary CTA.  After a run the hero and history
       section both refresh **in place** without a page reload.
    2. *Dimension scorecard* — one row per assessed dimension: score bar, trend arrow +
       delta (e.g. ↑+5%), classification label.
    3. *Risk factors* — severity-coloured list (CRITICAL / MAJOR / MINOR).
    4. *Rationale* — LLM-written narrative, collapsible.
    5. *Remediation plan* — numbered action-item list.
    6. *Source metrics* — brain-derived scope / SQ quality / E2E bars; open defect
       breakdown; weekly velocity; planned-vs-actual earned value.
    7. *Environment* — shared ``EnvironmentInput`` snapshot (component table).
    8. *Dependencies* — shared ``DependencyInput`` snapshot (dependency table).
    9. *Security* — shared ``SecurityInput`` posture (ADR-0016 gate-only dimension).
    10. *Assessment history* — past verdicts from SQLite with drill-in.

**History**
    Recent assessments from ``AssessmentStore.all_recent()``.  Programme and TOC value-
    stream filter buttons narrow the record pool.  Clicking a row opens the full verdict
    detail dialog (ADR-0022).

**Trends**
    Score-over-time line chart per release, built from brain snapshot history via
    ``score_over_snapshots()``.  Programme and TOC value-stream filters + release
    selector.

**Ingest** (admin, separated in sidebar)
    HTML report → brain JSON conversion.  Replicates ``rrr-ingest`` in the browser so
    operators never need to switch to the terminal (ADR-0018).

**Collect** (admin, separated in sidebar)
    Data collection for supplementary dimension JSON files (ADR-0023, M7 Phase 2).
    Shows a FRESH / STALE / MISSING status grid for all 14 supplementary dimensions,
    then renders InputContract-driven NiceGUI forms for editing.  Enum→select,
    bool→switch, int/float→number, str→input.  Save calls ``CollectorRunner.run()``
    to validate and write ``data/<dimension>.json``.

Selection model (ADR-0022) — three independent dimensions:
    1. **Dataset** — which brain file; resolved from ``?dataset=`` query parameter.
    2. **Programme** — filter row in Overview and History panels.
    3. **TOC value stream** — grouping and filter in History and Trends panels.

Local-first invariant (ADR-0010): the server binds to ``127.0.0.1`` by default.
All data comes from local JSON files and SQLite — no outbound network calls.
"""

from __future__ import annotations

import asyncio
import enum as enum_module
import inspect
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from rrr.collectors.base import BaseCollector, CollectorConfig
from rrr.collectors.registry import CollectorRegistry
from rrr.collectors.runner import CollectorRunner, CollectorStatus, DimensionStatusReport
from rrr.config.schema import FileSource, RRRConfig
from rrr.memory import AssessmentStore
from rrr.models.assessment import AssessmentOutputModel
from rrr.models.brain import ReleaseRecord
from rrr.models.dependency import DependencyInput
from rrr.models.enums import Verdict
from rrr.models.environment import EnvironmentInput
from rrr.models.security import SecurityInput
from rrr.pipeline import run_and_record
from rrr.tools import RKTBrainReader
from rrr.tools.source_reader import (
    DependencySourceReader,
    EnvironmentSourceReader,
    SecuritySourceReader,
)

logger = logging.getLogger(__name__)

# Quasar colour names for verdict chips — maps cleanly to Quasar's colour palette.
_VERDICT_COLOR: dict[Verdict, str] = {
    Verdict.GO: "positive",
    Verdict.NO_GO: "negative",
    Verdict.CONDITIONAL: "warning",
    Verdict.INCOMPLETE: "grey",
}

# Material icon names matched to each verdict label.
_VERDICT_ICON: dict[Verdict, str] = {
    Verdict.GO: "check_circle",
    Verdict.NO_GO: "cancel",
    Verdict.CONDITIONAL: "warning",
    Verdict.INCOMPLETE: "help_outline",
}

# Severity → Tailwind text-colour class for risk-factor bullets.
_SEV_COLOR: dict[str, str] = {
    "critical": "text-red-600",
    "major": "text-amber-600",
    "minor": "text-gray-500",
}

# Quasar colour for special Trends/History filter buttons that are not TOC VS names.
_TRENDS_SPECIAL_COLOR: dict[str, str] = {
    "All": "blue-grey",
    "Untagged": "grey",
}

# Inline CSS border+background for the Release Detail verdict hero card.
# Full strings ensure Tailwind JIT never strips them (inline style bypasses the purge).
_VERDICT_HERO_STYLE: dict[Verdict, str] = {
    Verdict.GO: "background:#f0fdf4;border:2px solid #86efac;border-radius:8px;",
    Verdict.NO_GO: "background:#fef2f2;border:2px solid #fca5a5;border-radius:8px;",
    Verdict.CONDITIONAL: "background:#fffbeb;border:2px solid #fcd34d;border-radius:8px;",
    Verdict.INCOMPLETE: "background:#f9fafb;border:2px solid #d1d5db;border-radius:8px;",
}

# Inline CSS colour for the hero score number and icon — verdict-specific tint.
_VERDICT_SCORE_STYLE: dict[Verdict, str] = {
    Verdict.GO: "color:#15803d;",
    Verdict.NO_GO: "color:#b91c1c;",
    Verdict.CONDITIONAL: "color:#b45309;",
    Verdict.INCOMPLETE: "color:#4b5563;",
}

# Verdict sort priority for the Overview table (lower = shown first).
_VERDICT_SORT_PRIORITY: dict[str, int] = {
    "NO_GO": 0,
    "CONDITIONAL": 1,
    "GO": 2,
    "INCOMPLETE": 3,
}

# Auto-filled fields on every InputContract — never presented to the user in the Collect form.
_AUTO_FIELDS: frozenset[str] = frozenset({"schema_version", "release", "captured_at"})

# Quasar chip colour per collector status badge.
_COLLECT_STATUS_COLOR: dict[CollectorStatus, str] = {
    CollectorStatus.FRESH: "positive",
    CollectorStatus.STALE: "warning",
    CollectorStatus.MISSING: "negative",
}

# Material icon per collector status badge.
_COLLECT_STATUS_ICON: dict[CollectorStatus, str] = {
    CollectorStatus.FRESH: "check_circle",
    CollectorStatus.STALE: "schedule",
    CollectorStatus.MISSING: "error_outline",
}


# ---------------------------------------------------------------------------
# Data helpers — no NiceGUI import, fully unit-testable in isolation
# ---------------------------------------------------------------------------


def load_releases(config: RRRConfig, value_stream: str) -> list[ReleaseRecord]:
    """Read all releases from the latest brain snapshot for the given value stream.

    Returns an empty list and logs a warning if the brain file is missing or
    invalid — a degraded dashboard is better than a crashed server.
    """
    reader = RKTBrainReader(config.sources.brain.dir)
    try:
        return reader.list_releases(value_stream)
    except Exception as exc:  # noqa: BLE001 — log and degrade gracefully
        logger.warning("Could not load releases for %r: %s", value_stream, exc)
        return []


def scope_pct(release: ReleaseRecord) -> float:
    """Return scope completion as a 0.0–1.0 fraction (closed / total).

    Uses the recomputed ratio rather than the upstream ``pct`` field so the
    displayed value is consistent with ``ScopeAssessor`` (ADR-0012).
    Returns 0.0 when ``total`` is zero to avoid division by zero.
    """
    total = release.summary.total
    if total == 0:
        return 0.0
    return min(1.0, release.summary.closed / total)


def e2e_pct(release: ReleaseRecord) -> float | None:
    """Return E2E pass rate as 0.0–1.0, or None when no E2E data exists.

    ``None`` is the distinguished absence signal — callers render "No data"
    rather than a zero bar, which would mislead the reader.
    """
    if release.e2e_latest is None:
        return None
    total = release.e2e_latest.passed + release.e2e_latest.failed
    if total == 0:
        return None
    return release.e2e_latest.passed / total


def sq_normalized(release: ReleaseRecord) -> float:
    """Normalise SQ average from the 0–3 SonarQube scale to a 0–1 fraction.

    The ``sq_avg`` field is Pydantic-constrained to ``[0, 3]``, so simple
    division is sufficient — no clamping required.
    """
    return release.sq_avg / 3.0


def score_over_snapshots(
    config: RRRConfig,
    release: str,
    value_stream: str,
) -> tuple[list[str], list[int]]:
    """Compute the deterministic score for a release at each brain snapshot date.

    Iterates all snapshot dates in the brain history file where the release
    appears, runs ``pipeline.assess()`` with ``RuleBasedProvider`` (no LLM, no
    SQLite write) for each date, and returns ``(dates, scores)`` oldest → newest.

    This is the primary data source for the Trends chart — it reflects how the
    release's readiness evolved across the weekly HTML ingests, independently of
    whether the user ever ran a manual assessment.
    """
    from rrr.pipeline import assess  # noqa: PLC0415
    from rrr.providers.rule_based import RuleBasedProvider  # noqa: PLC0415

    provider = RuleBasedProvider()
    reader = RKTBrainReader(config.sources.brain.dir)
    dates = reader.list_snapshot_dates(value_stream, ir_name=release)
    result_dates: list[str] = []
    result_scores: list[int] = []
    for date in dates:
        try:
            out = assess(
                config,
                release=release,
                value_stream=value_stream,
                snapshot=date,
                _provider=provider,
            )
            result_dates.append(date)
            result_scores.append(out.score)
        except Exception:  # noqa: BLE001
            # Skip snapshots where the release cannot be assessed (missing data).
            continue
    return result_dates, result_scores


def score_history_data(
    store: AssessmentStore,
    release: str,
    value_stream: str,
    *,
    limit: int = 20,
) -> tuple[list[str], list[int]]:
    """Return ``(timestamps, scores)`` for a release, ordered oldest → newest.

    ``timestamps`` are formatted ``YYYY-MM-DD HH:MM`` strings suitable for use
    as ECharts x-axis category labels.  ``scores`` are integers 0–100 matching
    the ``AssessmentOutputModel.score`` field.

    Returns two empty lists when no history exists so the chart renders an empty
    state rather than raising.

    Args:
        store: Open ``AssessmentStore`` to query.
        release: Exact release ir_name.
        value_stream: Value stream the release belongs to.
        limit: Maximum number of historical points to include (default 20).
    """
    records = store.history(release, value_stream, limit=limit)
    # history() returns newest-first; reverse for chronological chart rendering.
    records = list(reversed(records))
    timestamps = [r.generated_at.strftime("%Y-%m-%d %H:%M") for r in records]
    scores = [r.score for r in records]
    return timestamps, scores


def list_datasets(config: RRRConfig) -> list[str]:
    """Scan the brain directory and return all dataset labels found there.

    A dataset is any file matching ``brain/*-history.json``.  The label is the
    stem with the ``-history`` suffix removed (e.g. ``OSM-history.json`` →
    ``"OSM"``).  Returns an empty list when the directory does not exist or
    contains no matching files — callers must guard against this.
    """
    brain_dir = Path(config.sources.brain.dir)
    if not brain_dir.exists():
        return []
    return sorted(p.stem.removesuffix("-history") for p in brain_dir.glob("*-history.json"))


def list_programmes(releases: list[ReleaseRecord]) -> list[str]:
    """Return all distinct engineering-team programme codes found in releases.

    Codes are taken from ``release.programme`` (e.g. ``"OSM"``, ``"AIMS"``).
    The list is sorted alphabetically and excludes falsy values.  Returns an
    empty list when all releases have the same programme — in that case the
    filter row is not shown.
    """
    codes: set[str] = {r.programme for r in releases if r.programme}
    if len(codes) <= 1:
        return []
    return sorted(codes)


def vs_category(release: ReleaseRecord, config: RRRConfig) -> str:
    """Classify a release relative to the configured value stream.

    Returns one of ``'direct'``, ``'dependency'``, ``'supporting'``, or
    ``'other'``.  Priority (highest wins): direct → dependency → supporting →
    other.

    * **direct** — ``programme`` matches any VS alias (e.g. programme="OSM",
      alias="OS&M" both resolve to the same value stream).
    * **dependency** — ``release_relationship.dependency_for`` mentions any
      alias (e.g. "Onboarding Automation (Dependency for: OS&M; ...)").
    * **supporting** — ``programme`` is in ``related_programmes`` (e.g. AIMS,
      EIMS, PIMS releases that implement OSM features).
    * **other** — none of the above match (cross-programme releases with no
      direct link to the configured VS).

    When ``config.value_stream`` is ``None`` (registry not configured) every
    release returns ``'other'`` and the category filter is hidden in the UI.
    """
    vs_cfg = config.value_stream
    if vs_cfg is None:
        return "other"

    aliases_upper = [a.upper() for a in vs_cfg.aliases]

    if release.programme.upper() in aliases_upper:
        return "direct"

    rr = release.release_relationship
    if rr and rr.dependency_for:
        dep_upper = rr.dependency_for.upper()
        if any(a in dep_upper for a in aliases_upper):
            return "dependency"

    if release.programme in vs_cfg.related_programmes:
        return "supporting"

    return "other"


def load_environment(config: RRRConfig) -> EnvironmentInput | None:
    """Load the shared environment snapshot from the configured source.

    Returns ``None`` and logs a warning when the source file is missing, invalid
    JSON, or fails Pydantic validation — the UI renders a "not available" state
    rather than crashing the dashboard server.
    """
    src = config.sources.environment
    try:
        reader = (
            EnvironmentSourceReader(path=src.path)
            if isinstance(src, FileSource)
            else EnvironmentSourceReader(url=src.url)
        )
        result = reader.invoke()
        assert isinstance(result, EnvironmentInput)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load environment data: %s", exc)
        return None


def load_dependency(config: RRRConfig) -> DependencyInput | None:
    """Load the shared dependency snapshot from the configured source.

    Returns ``None`` and logs a warning on any read or validation failure —
    the UI renders a "not available" state rather than crashing.
    """
    src = config.sources.dependency
    try:
        reader = (
            DependencySourceReader(path=src.path)
            if isinstance(src, FileSource)
            else DependencySourceReader(url=src.url)
        )
        result = reader.invoke()
        assert isinstance(result, DependencyInput)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load dependency data: %s", exc)
        return None


def load_security_data(config: RRRConfig) -> SecurityInput | None:
    """Load the security posture snapshot if a security source is configured.

    The security source is opt-in (ADR-0016) — returns ``None`` both when the
    source is absent from config and when the source file cannot be read.
    """
    src = config.sources.security
    if src is None:
        # Security source not configured — UI will show a "not configured" message.
        return None
    try:
        reader = (
            SecuritySourceReader(path=src.path)
            if isinstance(src, FileSource)
            else SecuritySourceReader(url=src.url)
        )
        result = reader.invoke()
        assert isinstance(result, SecurityInput)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load security data: %s", exc)
        return None


def latest_for_release(
    store: AssessmentStore,
    release: str,
    value_stream: str,
) -> AssessmentOutputModel | None:
    """Return the most recent assessment for a release, or ``None`` when none exist.

    Used by the Release Detail screen to show the last known verdict without
    requiring a fresh assessment run.

    Args:
        store: Open ``AssessmentStore`` to query.
        release: Exact release ir_name.
        value_stream: Value stream the release belongs to.
    """
    records = store.history(release, value_stream, limit=1)
    return records[0] if records else None


def collect_status_all(
    data_dir: Path,
    staleness_days: int = 7,
) -> list[DimensionStatusReport]:
    """Return freshness status for all 14 supplementary dimensions (ADR-0023, M7 Phase 2).

    Instantiates a ``CollectorRegistry`` (all supplementary dimensions) and a
    ``CollectorRunner``, then scans ``data_dir`` for each dimension's JSON file.
    Returns one ``DimensionStatusReport`` per dimension in registry display order
    (operability → … → architecture_drift).

    Args:
        data_dir: Directory containing ``<dimension>.json`` files (typically ``./data``).
        staleness_days: Files older than this many days are reported as STALE.
    """
    registry = CollectorRegistry()
    runner = CollectorRunner(staleness_days=staleness_days)
    return runner.status(registry.dimensions(), data_dir)


def load_collect_form_data(data_dir: Path, dimension: str) -> dict[str, Any]:
    """Load the existing JSON data file for a dimension as a defaults dict.

    Returns the parsed dict when the file exists and is valid JSON.  Returns
    ``{}`` when the file is absent or unreadable so callers fall back to model
    field defaults (update-mode semantics: re-running the form shows prior values).

    Args:
        data_dir: Directory containing ``<dimension>.json`` files.
        dimension: Dimension name string (``DimensionName.value``), e.g. ``"operability"``.
    """
    path = data_dir / f"{dimension}.json"
    try:
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return result
    except (OSError, ValueError):
        # File absent, unreadable, or not valid JSON — treat as no prior data.
        return {}


# ---------------------------------------------------------------------------
# Ingest helper — runs synchronously in a thread-pool executor
# ---------------------------------------------------------------------------


def _run_ingest_sync(html_dir: Path, brain_dir: Path, value_stream: str) -> list[str]:
    """Run HTMLExtractor + BrainWriter for every HTML file in html_dir.

    Returns a list of human-readable status lines (one per processed file plus
    a summary line).  Raises ValueError or KeyError on a malformed HTML report.
    Called via ``run_in_executor`` so the NiceGUI event loop is not blocked.
    """
    from rrr.ingest.brain_writer import BrainWriter  # noqa: PLC0415
    from rrr.ingest.html_extractor import HTMLExtractor  # noqa: PLC0415

    extractor = HTMLExtractor()
    writer = BrainWriter()
    lines: list[str] = []

    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        return [f"No .html files found in {html_dir}"]

    processed = 0
    for html_path in html_files:
        try:
            date, releases = extractor.extract(html_path)
        except (ValueError, KeyError) as exc:
            # Not a valid RKT report (missing __REPORT__, wrong format, etc.) — skip it.
            lines.append(f"  SKIP  {html_path.name}  —  {exc}")
            continue
        out_path = writer.append_snapshot(brain_dir, value_stream, date, releases)
        lines.append(
            f"  OK    {html_path.name}  →  snapshot {date}"
            f"  ({len(releases)} releases)  →  {out_path}"
        )
        processed += 1

    if processed == 0:
        raise ValueError(
            f"No valid RKT Program Metrics reports found in {html_dir} "
            f"({len(html_files)} file(s) checked — all skipped)."
        )

    out_file = brain_dir / f"{value_stream}-history.json"
    lines.append(f"\nDone: {processed} of {len(html_files)} file(s) ingested into {out_file}")
    return lines


# ---------------------------------------------------------------------------
# NiceGUI rendering helpers (import nicegui lazily — only when rendering)
# ---------------------------------------------------------------------------


def _verdict_chip(verdict: Verdict) -> None:
    """Render a Quasar badge chip colour-coded by verdict label."""
    from nicegui import ui  # noqa: PLC0415

    color = _VERDICT_COLOR.get(verdict, "grey")
    icon = _VERDICT_ICON.get(verdict, "help_outline")
    label = verdict.value.replace("_", " ")
    ui.badge(label, color=color).props(f'icon="{icon}"')


def _metric_bar(label: str, value: float, *, warn_below: float = 0.5) -> None:
    """Render a mini labelled progress bar in the current container.

    Colour logic: red below ``warn_below − 0.10``, amber in the band
    ``[warn_below − 0.10, warn_below)``, green at or above ``warn_below``.
    This gives scope (warn_below=0.80) red at <70%, amber 70–79%, green ≥80%.
    """
    from nicegui import ui  # noqa: PLC0415

    if value < warn_below - 0.10:
        color = "negative"
    elif value < warn_below:
        color = "warning"
    else:
        color = "positive"

    with ui.column().classes("gap-0 w-full"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(label).classes("text-xs text-gray-500")
            ui.label(f"{value:.0%}").classes("text-xs font-semibold")
        ui.linear_progress(value=value, color=color).classes("w-full").style("height:6px")


def _verdict_card(result: AssessmentOutputModel, container: Any) -> None:
    """Clear ``container`` and render the full verdict card into it.

    ``container`` must be a NiceGUI element that supports ``.clear()`` and
    acts as a context manager (e.g. ``ui.column()``).  Called after both a
    freshly run assessment and a history drill-in.
    """
    from nicegui import ui  # noqa: PLC0415

    container.clear()
    with container:
        with ui.column().classes("gap-3 w-full"):
            # Header row: release name + verdict chip
            with ui.row().classes("items-center justify-between w-full flex-wrap gap-2"):
                ui.label(result.release).classes("text-xl font-bold")
                _verdict_chip(result.verdict)

            # Overall score bar
            with ui.row().classes("items-center gap-3 w-full"):
                ui.label(f"Score  {result.score}/100").classes("text-sm font-medium w-32 shrink-0")
                ui.linear_progress(value=result.score / 100).classes("flex-1")

            # Confidence bar (only when available)
            if result.aggregate_confidence is not None:
                conf_pct = f"{result.aggregate_confidence:.0%}"
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.label(f"Confidence  {conf_pct}").classes("text-sm font-medium w-32 shrink-0")
                    ui.linear_progress(
                        value=result.aggregate_confidence, color="secondary"
                    ).classes("flex-1")

            # Per-dimension breakdown
            if result.dimensions:
                ui.separator()
                ui.label("Dimensions").classes(
                    "text-xs font-semibold text-gray-400 uppercase tracking-wide"
                )
                for dim in result.dimensions:
                    name = dim.dimension.replace("_", " ").title()
                    if dim.available:
                        with ui.row().classes("items-center gap-3 w-full"):
                            ui.label(f"✅  {name}").classes("text-sm w-40 shrink-0")
                            ui.linear_progress(value=dim.score).classes("flex-1")
                            ui.label(f"{dim.score:.0%}").classes("text-sm w-10 text-right shrink-0")
                    else:
                        ui.label(f"—  {name}").classes("text-sm text-gray-400")

            # Risk factors
            if result.risk_factors:
                ui.separator()
                ui.label("Risk Factors").classes(
                    "text-xs font-semibold text-gray-400 uppercase tracking-wide"
                )
                for rf in result.risk_factors:
                    cls = _SEV_COLOR.get(rf.severity.value, "text-gray-500")
                    ui.label(f"• {rf.description}").classes(f"text-sm {cls}")

            # Rationale (collapsed by default — can be long)
            if result.rationale:
                with ui.expansion("Rationale", icon="psychology").classes("w-full border rounded"):
                    ui.label(result.rationale).classes(
                        "text-sm text-gray-700 whitespace-pre-wrap p-2"
                    )

            # Remediation checklist
            if result.remediation:
                with ui.expansion("Remediation Plan", icon="build").classes(
                    "w-full border rounded"
                ):
                    for item in result.remediation:
                        ui.label(f"• {item}").classes("text-sm text-gray-700 p-1")


def _provision_color(status: str) -> str:
    """Map a ``ProvisioningStatus`` value to a Quasar badge colour name."""
    mapping = {
        "validated": "positive",
        "provisioned": "positive",
        "configured": "blue",
        "missing": "negative",
    }
    return mapping.get(status, "grey")


def _stability_color(status: str) -> str:
    """Map a ``StabilityStatus`` value to a Quasar badge colour name."""
    mapping = {
        "stable": "positive",
        "degraded": "warning",
        "down": "negative",
    }
    return mapping.get(status, "grey")


def _completion_color(status: str) -> str:
    """Map a ``DependencyCompletion`` value to a Quasar badge colour name."""
    mapping = {
        "complete": "positive",
        "in_progress": "warning",
        "not_started": "negative",
    }
    return mapping.get(status, "grey")


def _integration_color(status: str) -> str:
    """Map an ``IntegrationStatus`` value to a Quasar badge colour name."""
    mapping = {
        "passed": "positive",
        "not_validated": "grey",
        "failed": "negative",
    }
    return mapping.get(status, "grey")


# ---------------------------------------------------------------------------
# Shared section renderers — used by Release Detail and the old detail panel
# ---------------------------------------------------------------------------


def _detail_environment(env_data: EnvironmentInput | None) -> None:
    """Render the Environment section body.

    Shows each component's provisioning and stability state from the shared
    environment snapshot.  Shared means this snapshot covers all releases, not
    a specific one — a banner reminds the reader.
    """
    from nicegui import ui  # noqa: PLC0415

    ui.label(
        "Shared snapshot — applies to all releases in this programme, not release-specific."
    ).classes("text-xs text-amber-600 italic mb-3")

    if env_data is None:
        with ui.column().classes("items-center gap-2 py-10 text-gray-400"):
            ui.icon("cloud_off").classes("text-5xl")
            ui.label("Environment data unavailable.").classes("text-sm")
            ui.label("Check that data/environment.json exists and is readable.").classes("text-xs")
        return

    if env_data.captured_at:
        ui.label(f"Captured: {env_data.captured_at}").classes("text-xs text-gray-400 mb-2")

    # Component rows with coloured status badges.
    for comp in env_data.components:
        with ui.row().classes("items-center gap-3 border-b py-2 flex-wrap"):
            ui.label(comp.name).classes("font-medium text-sm min-w-[10rem]")
            prov = comp.provisioning.value
            ui.badge(prov, color=_provision_color(prov))
            stab = comp.stability.value
            ui.badge(stab, color=_stability_color(stab))
            if comp.notes:
                ui.label(comp.notes).classes("text-xs text-gray-500")


def _detail_dependencies(dep_data: DependencyInput | None) -> None:
    """Render the Dependencies section body.

    Shows each dependency's completion and integration-validation state from the
    shared dependency snapshot.  A shared-snapshot banner is displayed, as the
    file is not per-release.
    """
    from nicegui import ui  # noqa: PLC0415

    ui.label(
        "Shared snapshot — applies to all releases in this programme, not release-specific."
    ).classes("text-xs text-amber-600 italic mb-3")

    if dep_data is None:
        with ui.column().classes("items-center gap-2 py-10 text-gray-400"):
            ui.icon("link_off").classes("text-5xl")
            ui.label("Dependency data unavailable.").classes("text-sm")
            ui.label("Check that data/dependency.json exists and is readable.").classes("text-xs")
        return

    if dep_data.captured_at:
        ui.label(f"Captured: {dep_data.captured_at}").classes("text-xs text-gray-400 mb-2")

    # Dependency rows with coloured completion and integration badges.
    for dep in dep_data.dependencies:
        with ui.row().classes("items-center gap-3 border-b py-2 flex-wrap"):
            ui.label(dep.name).classes("font-medium text-sm min-w-[10rem]")
            comp = dep.completion.value
            ui.badge(comp.replace("_", " "), color=_completion_color(comp))
            intg = dep.integration.value
            ui.badge(intg.replace("_", " "), color=_integration_color(intg))
            if dep.owner:
                ui.label(f"Owner: {dep.owner}").classes("text-xs text-gray-500")
            if dep.notes:
                ui.label(dep.notes).classes("text-xs text-gray-400")


def _detail_security(sec_data: SecurityInput | None) -> None:
    """Render the Security section body.

    Shows SAST/DAST scan outcomes, open CVE counts, and approval flags from the
    shared security posture snapshot (ADR-0016, gate-only dimension).  Displays
    a "not configured" message when ``sources.security`` is absent from config.
    """
    from nicegui import ui  # noqa: PLC0415

    if sec_data is None:
        with ui.column().classes("items-center gap-2 py-10 text-gray-400"):
            ui.icon("security").classes("text-5xl")
            ui.label("Security source not configured.").classes("text-sm")
            ui.label(
                "Add sources.security to your config"
                " (e.g. data/security.json) to enable this section."
            ).classes("text-xs text-center max-w-xs")
        return

    ui.label(
        "Shared snapshot — applies to all releases in this programme, not release-specific."
    ).classes("text-xs text-amber-600 italic mb-3")

    if sec_data.captured_at:
        ui.label(f"Captured: {sec_data.captured_at}").classes("text-xs text-gray-400 mb-2")

    # SAST / DAST scan outcomes
    def _scan_row(label: str, status: str) -> None:
        """Render one scan-result row with a coloured badge."""
        color_map = {"passed": "positive", "failed": "negative", "not_run": "grey"}
        with ui.row().classes("items-center gap-3 border-b py-1"):
            ui.label(label).classes("text-sm min-w-[8rem]")
            ui.badge(status.replace("_", " "), color=color_map.get(status, "grey"))

    _scan_row("SAST", sec_data.sast_status.value)
    _scan_row("DAST", sec_data.dast_status.value)

    # CVE counts
    with ui.row().classes("items-center gap-6 border-b py-2"):
        # Red when any critical CVE is open; green when clear.
        crit_cls = (
            "text-red-600 font-semibold" if sec_data.open_critical_cves > 0 else "text-green-600"
        )
        ui.label(f"Critical CVEs: {sec_data.open_critical_cves}").classes(f"text-sm {crit_cls}")
        ui.label(f"High CVEs: {sec_data.open_high_cves}").classes("text-sm")

    # Approval flags — tri-state: True / False / None (pending)
    def _approval_row(label: str, approved: bool | None) -> None:
        """Render one approval flag as a coloured badge."""
        if approved is True:
            ui.badge("approved", color="positive")
        elif approved is False:
            ui.badge("not approved", color="negative")
        else:
            ui.badge("pending", color="grey")
        ui.label(label).classes("text-sm")

    with ui.row().classes("items-center gap-3 border-b py-1"):
        _approval_row("License", sec_data.license_approved)

    with ui.row().classes("items-center gap-3 border-b py-1"):
        _approval_row("Data Privacy", sec_data.data_privacy_approved)

    with ui.row().classes("items-center gap-3 py-1"):
        _approval_row("Pen Test", sec_data.pen_test_passed)


# ---------------------------------------------------------------------------
# Collect screen support — dict collector + type-dispatch helpers
# ---------------------------------------------------------------------------


class _DictCollector(BaseCollector):
    """Minimal ``BaseCollector`` that returns a pre-built dict (M7 Phase 2 Collect screen).

    The Collect form builds a data dict from NiceGUI widget values, then routes it
    through ``CollectorRunner.run()`` via this wrapper so the validation and write
    logic stays in one place.  Collectors themselves should never write files
    directly (ADR-0023).
    """

    def __init__(self, dim: str, data: dict[str, Any]) -> None:
        """Bind to one dimension and its pre-built data dict.

        Args:
            dim: ``DimensionName.value`` string (e.g. ``"operability"``).
            data: Raw dict returned verbatim from ``collect()``.
        """
        self._dim = dim
        self._data = data

    @property
    def dimension(self) -> str:
        """Return the dimension name this collector targets."""
        return self._dim

    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Return the pre-built dict; ``CollectorRunner.run()`` validates and writes it."""
        return self._data


def _unwrap_collect_optional(annotation: Any) -> tuple[Any, bool]:
    """Extract the inner type from ``Optional[T]`` (i.e. ``Union[T, None]``).

    Returns ``(inner_type, True)`` when the annotation is ``Optional[T]`` and
    ``(annotation, False)`` for all other types (including bare, non-optional ones).
    Mirrors the logic in ``InteractiveCollector`` so widget dispatch behaves
    identically in the NiceGUI form and the Click CLI.
    """
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0], True
    return annotation, False


def _build_collect_field_widget(
    name: str,
    field_info: Any,
    inner_type: Any,
    existing_val: Any,
) -> Any:
    """Build one NiceGUI input widget for a single ``InputContract`` field.

    Returns the bound widget so its ``.value`` can be read at save time.
    Returns ``None`` for dict/list fields that cannot be collected interactively
    — the caller renders an advisory note for those.

    Dispatch order: Enum subclass → ``ui.select``; bool → ``ui.switch``;
    int → ``ui.number`` (integer); float → ``ui.number`` (decimal); str → ``ui.input``.
    """
    from nicegui import ui  # noqa: PLC0415

    desc = (field_info.description or name).split(" (")[0]  # trim ADR refs
    label = f"{name.replace('_', ' ').title()} — {desc}"

    # Complex types (dict, list) cannot be collected interactively.
    if inner_type in (dict, list) or get_origin(inner_type) in (dict, list):
        ui.label(f"  {name}: complex type — edit this field in the JSON file").classes(
            "text-xs text-gray-400 italic"
        )
        return None

    if inspect.isclass(inner_type) and issubclass(inner_type, enum_module.Enum):
        choices = [e.value for e in inner_type]
        default = (
            existing_val.value
            if isinstance(existing_val, enum_module.Enum)
            else (
                existing_val
                if isinstance(existing_val, str) and existing_val in choices
                else choices[0]
            )
        )
        return ui.select(choices, value=default, label=label).classes("w-full")

    if inner_type is bool:
        return ui.switch(label, value=bool(existing_val) if existing_val is not None else False)

    if inner_type is int:
        return ui.number(label, value=int(existing_val) if existing_val is not None else 0,
                         format="%.0f").classes("w-full")

    if inner_type is float:
        return ui.number(label,
                         value=float(existing_val) if existing_val is not None else 0.0).classes(
            "w-full"
        )

    if inner_type is str:
        default_str = str(existing_val) if existing_val is not None else ""
        return ui.input(label, value=default_str).classes("w-full")

    # Unsupported type — skip with advisory message.
    ui.label(f"  {name}: unsupported type ({inner_type!r}) — edit JSON directly").classes(
        "text-xs text-gray-400 italic"
    )
    return None


# ---------------------------------------------------------------------------
# Sidebar navigation helper
# ---------------------------------------------------------------------------


def _nav_item(
    view: str,
    icon: str,
    label: str,
    active: bool,
    navigate_fn: Callable[..., None],
) -> None:
    """Render one sidebar nav item with icon above label and active-state styling.

    Active item has a blue-tinted background and blue text.  Inactive items show
    a grey hover state.  The click handler calls ``navigate_fn(view)`` to switch
    the content area.
    """
    from nicegui import ui  # noqa: PLC0415

    bg = "bg-blue-100" if active else "hover:bg-gray-200"
    text_cls = "text-blue-700 font-semibold" if active else "text-gray-600"
    # Use a plain div for full control over flex direction and gap without
    # NiceGUI's default column gap-4 interfering.
    with (
        ui.element("div")
        .classes(
            f"flex flex-col items-center w-full py-3 px-1 cursor-pointer gap-1 rounded-lg {bg}"
        )
        .on("click", lambda v=view: navigate_fn(v))
    ):
        ui.icon(icon).classes(f"text-2xl {text_cls}")
        ui.label(label).classes(f"text-[11px] font-medium {text_cls} leading-tight text-center")


# ---------------------------------------------------------------------------
# Overview panel — home screen with stats row + sortable release table
# ---------------------------------------------------------------------------


def _stat_card(
    value: str, label: str, icon_name: str = "", color_cls: str = "text-gray-700"
) -> None:
    """Render one summary stat card with icon, large value, and a small label.

    Used in the Overview panel health summary row.  Each card stretches equally
    with ``flex-1`` so the row fills the full width.
    """
    from nicegui import ui  # noqa: PLC0415

    with ui.card().props("flat bordered").classes("flex-1 min-w-[7rem]"):
        with ui.element("div").classes("flex flex-col items-center gap-1 p-4"):
            if icon_name:
                ui.icon(icon_name).classes(f"text-3xl {color_cls}")
            ui.label(value).classes(f"text-3xl font-bold {color_cls}")
            ui.label(label).classes("text-xs text-gray-500 uppercase tracking-wide text-center")


def _overall_trend(assessment: AssessmentOutputModel) -> tuple[str, str]:
    """Compute overall readiness trend direction from the assessment's dimension deltas.

    Returns ``(arrow_symbol, tailwind_colour_class)`` where the arrow is ↑, ↓, or →.
    A release is improving when the mean delta across available dimension trends
    exceeds 0.05 (5 percentage points); degrading when it is below −0.05.
    Returns ``("—", "text-gray-400")`` when no trend data is available.
    """
    if not assessment.trend_data:
        return ("—", "text-gray-400")
    avg_delta = sum(t.delta for t in assessment.trend_data) / len(assessment.trend_data)
    if avg_delta > 0.05:
        return ("↑", "text-green-600")
    if avg_delta < -0.05:
        return ("↓", "text-red-600")
    return ("→", "text-gray-500")


def _overview_panel(
    all_releases: list[ReleaseRecord],
    config: RRRConfig,
    value_stream: str,
    navigate_fn: Callable[..., None],
) -> None:
    """Render the Overview home screen: health stats row + filterable release table.

    Queries SQLite once to build a ``latest_map`` keyed by release name.  Assessed
    releases are sorted by urgency (NO-GO → CONDITIONAL → GO → INCOMPLETE) then by
    descending score; unassessed releases follow alphabetically, greyed out.

    The search input and verdict/TOC-VS selectors mutate a shared ``filter_state``
    dict and trigger ``_rebuild_table()`` to clear and re-render only the table rows
    without touching the stats row or filter controls.
    """
    from nicegui import ui  # noqa: PLC0415

    # Load latest assessment for every release in one SQLite query.
    store = AssessmentStore(config.memory.sqlite_path)
    try:
        recent = store.all_recent(value_stream=value_stream, limit=500)
    finally:
        store.close()

    latest_map: dict[str, AssessmentOutputModel] = {}
    for rec in recent:
        if rec.release not in latest_map:
            latest_map[rec.release] = rec

    # Stats for the summary row.
    release_names = {r.ir_name for r in all_releases}
    assessed_names = set(latest_map.keys())
    nogo_count = sum(
        1 for a in latest_map.values() if a.verdict == Verdict.NO_GO and a.release in release_names
    )
    cond_count = sum(
        1
        for a in latest_map.values()
        if a.verdict == Verdict.CONDITIONAL and a.release in release_names
    )
    unassessed_count = len(release_names - assessed_names)

    # --- Summary stats row ---
    ui.label("Overview").classes("text-2xl font-bold text-gray-800 mb-1")
    ui.label("Release health at a glance — click any row to view the full assessment.").classes(
        "text-sm text-gray-500 mb-5"
    )

    with ui.row().classes("w-full gap-4 mb-6 flex-wrap"):
        _stat_card(str(len(all_releases)), "Total releases", "rocket_launch")
        _stat_card(
            str(nogo_count),
            "NO-GO",
            "cancel",
            "text-red-600" if nogo_count > 0 else "text-gray-400",
        )
        _stat_card(
            str(cond_count),
            "Conditional",
            "warning",
            "text-amber-500" if cond_count > 0 else "text-gray-400",
        )
        _stat_card(
            str(unassessed_count),
            "Not assessed",
            "help_outline",
            "text-gray-500",
        )

    if not all_releases:
        with ui.column().classes("items-center gap-2 py-12 text-gray-400"):
            ui.icon("rocket_launch").classes("text-5xl")
            ui.label("No releases found.").classes("text-base")
            ui.label(
                "Check brain directory and value-stream config, or use Ingest to load data."
            ).classes("text-sm text-center max-w-xs")
        return

    # --- Filter controls ---
    filter_state: dict[str, str] = {"search": "", "verdict": "All", "toc_vs": "All"}

    toc_vs_values = sorted({r.toc_value_stream for r in all_releases if r.toc_value_stream})
    toc_vs_opts = {"All": "All value streams"} | {v: v for v in toc_vs_values}
    verdict_opts = {
        "All": "All verdicts",
        "GO": "GO",
        "NO_GO": "NO-GO",
        "CONDITIONAL": "Conditional",
        "Not assessed": "Not assessed",
    }

    with ui.row().classes("w-full items-center gap-3 mb-3 flex-wrap"):
        search_inp = (
            ui.input(placeholder="Search releases…")
            .props("outlined dense clearable")
            .classes("flex-1 min-w-[12rem]")
        )
        verdict_sel = (
            ui.select(verdict_opts, value="All").props("outlined dense").classes("min-w-[9rem]")
        )
        if len(toc_vs_values) > 0:
            toc_sel: Any = (
                ui.select(toc_vs_opts, value="All").props("outlined dense").classes("min-w-[12rem]")
            )
        else:
            toc_sel = None

    # --- Table ---
    table_col = ui.column().classes("w-full border rounded-lg overflow-hidden")

    def _get_filtered() -> list[ReleaseRecord]:
        """Apply current filter_state to all_releases and return the matching subset."""
        search = filter_state["search"].lower()
        verdict_f = filter_state["verdict"]
        toc_f = filter_state["toc_vs"]

        result: list[ReleaseRecord] = []
        for rel in all_releases:
            if search and search not in rel.ir_name.lower():
                continue
            if toc_f != "All" and (rel.toc_value_stream or "") != toc_f:
                continue
            if verdict_f != "All":
                la = latest_map.get(rel.ir_name)
                if verdict_f == "Not assessed":
                    if la is not None:
                        continue
                elif la is None or la.verdict.value != verdict_f:
                    continue
            result.append(rel)
        return result

    def _rebuild_table() -> None:
        """Clear the table area and re-render rows for the current filter state."""
        filtered = _get_filtered()
        table_col.clear()
        with table_col:
            # Header row
            with ui.element("div").classes(
                "flex items-center px-4 py-2 bg-gray-100 border-b gap-3"
            ):
                ui.label("Release").classes("flex-1 text-xs font-semibold text-gray-500 uppercase")
                ui.label("Score").classes(
                    "w-14 text-xs font-semibold text-gray-500 uppercase text-right"
                )
                ui.label("Verdict").classes("w-36 text-xs font-semibold text-gray-500 uppercase")
                ui.label("Trend").classes(
                    "w-12 text-xs font-semibold text-gray-500 uppercase text-center"
                )
                ui.label("Assessed").classes(
                    "w-24 text-xs font-semibold text-gray-500 uppercase text-right"
                )

            assessed_rows = [r for r in filtered if r.ir_name in latest_map]
            unassessed_rows = [r for r in filtered if r.ir_name not in latest_map]

            # Sort assessed by urgency then descending score.
            assessed_rows.sort(
                key=lambda r: (
                    _VERDICT_SORT_PRIORITY.get(latest_map[r.ir_name].verdict.value, 4),
                    -(latest_map[r.ir_name].score),
                )
            )
            unassessed_rows.sort(key=lambda r: r.ir_name)

            for rel in assessed_rows:
                la = latest_map[rel.ir_name]
                now = datetime.now(tz=UTC)
                age_days = (now - la.generated_at).days
                if age_days == 0:
                    age_str = "Today"
                elif age_days < 30:
                    age_str = f"{age_days}d ago"
                else:
                    age_str = f"{age_days // 30}mo ago"

                score_cls = (
                    "text-green-700 font-bold"
                    if la.score >= 80
                    else "text-amber-600 font-bold"
                    if la.score >= 40
                    else "text-red-600 font-bold"
                )
                arrow, arrow_cls = _overall_trend(la)

                with (
                    ui.element("div")
                    .classes(
                        "flex items-center px-4 py-3 border-b gap-3 cursor-pointer hover:bg-blue-50"
                    )
                    .on("click", lambda r=rel: navigate_fn("detail", r))
                ):
                    with ui.element("div").classes("flex-1 flex flex-col gap-0 min-w-0"):
                        ui.label(rel.ir_name).classes("text-sm font-medium text-gray-800")
                        with ui.element("div").classes("flex items-center gap-2"):
                            if rel.programme:
                                ui.label(f"[{rel.programme}]").classes("text-xs text-gray-400")
                            if rel.toc_value_stream:
                                ui.label(rel.toc_value_stream).classes("text-xs text-gray-400")
                    ui.label(str(la.score)).classes(f"w-14 text-sm {score_cls} text-right")
                    with ui.element("div").classes("w-36"):
                        _verdict_chip(la.verdict)
                    ui.label(arrow).classes(f"w-12 text-sm {arrow_cls} text-center font-bold")
                    ui.label(age_str).classes("w-24 text-xs text-gray-400 text-right")

            for rel in unassessed_rows:
                with (
                    ui.element("div")
                    .classes(
                        "flex items-center px-4 py-3 border-b gap-3"
                        " cursor-pointer opacity-50 hover:bg-gray-50"
                    )
                    .on("click", lambda r=rel: navigate_fn("detail", r))
                ):
                    with ui.element("div").classes("flex-1 flex flex-col gap-0 min-w-0"):
                        ui.label(rel.ir_name).classes("text-sm font-medium text-gray-600")
                        with ui.element("div").classes("flex items-center gap-2"):
                            if rel.programme:
                                ui.label(f"[{rel.programme}]").classes("text-xs text-gray-400")
                    ui.label("—").classes("w-14 text-sm text-gray-300 text-right")
                    ui.label("Not assessed").classes("w-36 text-xs text-gray-400 italic")
                    ui.label("—").classes("w-12 text-xs text-gray-300 text-center")
                    ui.label("Never").classes("w-24 text-xs text-gray-400 text-right")

            if not filtered:
                with ui.element("div").classes("flex flex-col items-center gap-2 py-10"):
                    ui.icon("search_off").classes("text-4xl text-gray-300")
                    ui.label("No releases match this filter.").classes("text-sm text-gray-400")

    # Wire filter event handlers — read widget .value directly (avoids GenericEventArguments.
    # NiceGUI's .on("update:model-value") yields GenericEventArguments which has no .value).
    def _on_search(_e: Any) -> None:
        """Update the search term and refresh the table."""
        filter_state["search"] = search_inp.value or ""
        _rebuild_table()

    def _on_verdict(_e: Any) -> None:
        """Update the verdict filter and refresh the table."""
        filter_state["verdict"] = verdict_sel.value or "All"
        _rebuild_table()

    def _on_toc(_e: Any) -> None:
        """Update the TOC value-stream filter and refresh the table."""
        if toc_sel is not None:
            filter_state["toc_vs"] = toc_sel.value or "All"
        _rebuild_table()

    search_inp.on("update:model-value", _on_search)
    verdict_sel.on("update:model-value", _on_verdict)
    if toc_sel is not None:
        toc_sel.on("update:model-value", _on_toc)

    # Initial table render.
    _rebuild_table()


# ---------------------------------------------------------------------------
# Release Detail screen — single scrollable page replacing nested tabs
# ---------------------------------------------------------------------------


def _release_detail(
    release: ReleaseRecord,
    config: RRRConfig,
    vs: str,
    env_data: EnvironmentInput | None,
    dep_data: DependencyInput | None,
    sec_data: SecurityInput | None,
    latest: AssessmentOutputModel | None,
    hist_records_in: list[AssessmentOutputModel],
    navigate: Any,
) -> None:
    """Render the Release Detail screen as a single scrollable column.

    Sections (verdict hero → dimensions → risks → rationale → remediation →
    source metrics → environment → dependencies → security → history) are
    rendered in one pass; no inner tabs.

    The verdict hero area and history area are both mutable (``ui.column()``
    instances that can be cleared and rebuilt).  Calling ``Run Assessment``
    triggers ``_run_assessment()`` which refreshes both in place without
    navigating away.

    Args:
        release: The selected ``ReleaseRecord`` from the brain snapshot.
        config: Validated ``RRRConfig`` (pipeline config + memory path).
        vs: Active dataset / value stream label.
        env_data: Pre-loaded environment snapshot, or ``None`` if unavailable.
        dep_data: Pre-loaded dependency snapshot, or ``None`` if unavailable.
        sec_data: Pre-loaded security posture, or ``None`` if not configured.
        latest: Most recent assessment from SQLite, or ``None`` if none exist.
        hist_records_in: Historical assessments for this release (newest first).
        navigate: Callback ``(view, release=None)`` that swaps the content area.
    """
    from nicegui import ui  # noqa: PLC0415

    # Local mutable copy — _refresh_history prepends new results to it.
    hist_records: list[AssessmentOutputModel] = list(hist_records_in)

    # --- Persistent dialogs (created once, opened/closed by callbacks) ---

    with ui.dialog().props("persistent") as loading_dlg, ui.card():
        with ui.element("div").classes("flex flex-col items-center gap-4 p-8"):
            ui.spinner(size="xl")
            ui.label("Running assessment…").classes("text-base text-gray-600")

    result_hist_col: Any
    with (
        ui.dialog().props("full-width") as result_hist_dlg,
        ui.card().classes("w-full max-w-2xl p-6"),
    ):
        with ui.column().classes("w-full gap-4"):
            result_hist_col = ui.column().classes("w-full")
            ui.button("Close", icon="close", on_click=result_hist_dlg.close).classes("self-end")

    # --- Async assessment runner ---

    async def _run_assessment() -> None:
        """Run pipeline.run_and_record in a thread pool, then refresh hero and history."""
        loading_dlg.open()
        loop = asyncio.get_event_loop()
        try:
            out: AssessmentOutputModel = await loop.run_in_executor(
                None,
                partial(run_and_record, config, release=release.ir_name, value_stream=vs),
            )
        except Exception as exc:  # noqa: BLE001
            # Network or pipeline errors must not crash the server.
            loading_dlg.close()
            ui.notify(f"Assessment failed: {exc}", type="negative", timeout=10_000)
            return
        loading_dlg.close()
        _refresh_verdict(out)
        _refresh_history(out)
        ui.notify(
            f"Assessment complete: {out.verdict.value.replace('_', ' ')}  ({out.score}/100)",
            type="positive",
        )

    # --- Breadcrumb / page header row ---

    with ui.element("div").classes("flex items-center gap-2 mb-6 flex-wrap"):
        ui.button(icon="arrow_back", on_click=lambda: navigate("overview")).props(
            "flat round dense"
        )
        ui.label("Overview").classes("text-sm text-blue-600 cursor-pointer hover:underline").on(
            "click", lambda: navigate("overview")
        )
        ui.label("/").classes("text-sm text-gray-300")
        ui.label(release.ir_name).classes("text-sm font-semibold text-gray-800")
        if release.programme:
            ui.label(f"[{release.programme}]").classes("text-sm text-gray-400")
        ui.element("div").classes("flex-1")
        ui.button(
            "Run Assessment",
            icon="play_arrow",
            color="primary",
            on_click=_run_assessment,
        ).props("unelevated").classes("shrink-0")

    # --- Verdict hero area (refreshable) ---

    verdict_area = ui.column().classes("w-full mb-4")

    def _section_hdr(title: str) -> None:
        """Render a small-caps section divider with a horizontal rule below."""
        ui.label(title).classes(
            "text-xs font-semibold text-gray-400 uppercase tracking-widest mt-6 mb-1"
        )
        ui.separator().classes("mb-3")

    def _render_verdict_content(result: AssessmentOutputModel | None) -> None:
        """Build verdict hero card plus assessment sections (dimensions, risks, etc.)."""
        if result is None:
            with ui.card().props("flat bordered").classes("w-full"):
                with ui.element("div").classes("flex flex-col items-center gap-4 py-12"):
                    ui.icon("play_circle_outline").classes("text-6xl text-gray-300")
                    ui.label("No assessment recorded yet").classes("text-xl text-gray-500")
                    ui.label("Click Run Assessment above to generate the first verdict.").classes(
                        "text-sm text-gray-400"
                    )
            return

        # Hero card — colour-coded by verdict using inline style to guarantee rendering.
        hero_style = _VERDICT_HERO_STYLE.get(
            result.verdict,
            "background:#f9fafb;border:2px solid #d1d5db;border-radius:8px;",
        )
        score_style = _VERDICT_SCORE_STYLE.get(result.verdict, "color:#4b5563;")
        icon_name = _VERDICT_ICON.get(result.verdict, "help_outline")

        with ui.element("div").classes("w-full p-6").style(hero_style):
            with ui.element("div").classes(
                "flex items-center justify-between w-full flex-wrap gap-6"
            ):
                with ui.element("div").classes("flex items-center gap-4"):
                    ui.icon(icon_name).classes("text-5xl shrink-0").style(score_style)
                    with ui.element("div").classes("flex flex-col gap-0"):
                        ui.label(result.verdict.value.replace("_", " ")).classes(
                            "text-3xl font-bold text-gray-800"
                        )
                        ts = result.generated_at.strftime("%Y-%m-%d  %H:%M  UTC")
                        ui.label(f"Assessed  {ts}").classes("text-sm text-gray-500")
                with ui.element("div").classes("flex flex-col items-end gap-0"):
                    with ui.element("div").classes("flex items-baseline gap-2"):
                        ui.label(str(result.score)).classes("text-5xl font-bold").style(score_style)
                        ui.label("/ 100").classes("text-base text-gray-400")
                    if result.aggregate_confidence is not None:
                        ui.label(f"Confidence: {result.aggregate_confidence:.0%}").classes(
                            "text-sm text-gray-500 mt-1"
                        )

        # Dimension scorecard
        if result.dimensions:
            _section_hdr("DIMENSIONS")
            for dim in result.dimensions:
                dim_name = dim.dimension.replace("_", " ").title()
                with ui.element("div").classes("flex items-center gap-3 w-full py-2 border-b"):
                    ui.label(dim_name).classes("text-sm font-medium w-36 shrink-0")
                    if dim.available:
                        bar_color = (
                            "positive"
                            if dim.score >= 0.8
                            else "warning"
                            if dim.score >= 0.5
                            else "negative"
                        )
                        ui.linear_progress(value=dim.score, color=bar_color).classes("flex-1")
                        ui.label(f"{dim.score:.0%}").classes(
                            "text-sm font-semibold text-gray-700 w-12 text-right shrink-0"
                        )
                        # Trend arrow from the assessment's trend_data list.
                        td = next(
                            (t for t in result.trend_data if t.dimension == dim.dimension),
                            None,
                        )
                        if td is not None:
                            if td.delta > 0.05:
                                arrow_str, a_cls = f"↑+{td.delta:.0%}", "text-green-600"
                            elif td.delta < -0.05:
                                arrow_str, a_cls = f"↓{td.delta:.0%}", "text-red-600"
                            else:
                                arrow_str, a_cls = "→", "text-gray-400"
                            ui.label(arrow_str).classes(
                                f"text-xs font-bold {a_cls} w-16 text-right shrink-0"
                            )
                        else:
                            ui.label("—").classes("text-xs text-gray-300 w-16 text-right shrink-0")
                        if dim.classification:
                            ui.label(dim.classification).classes(
                                "text-xs text-gray-400 italic ml-2"
                            )
                    else:
                        ui.label("—  unavailable").classes("text-sm text-gray-400")

        # Risk factors
        if result.risk_factors:
            _section_hdr("RISK FACTORS")
            for rf in result.risk_factors:
                sev = rf.severity.value.lower()
                sev_cls = _SEV_COLOR.get(sev, "text-gray-500")
                with ui.element("div").classes("flex items-start gap-3 py-1"):
                    ui.label(rf.severity.value.upper()).classes(
                        f"text-xs font-bold w-16 shrink-0 mt-0.5 {sev_cls}"
                    )
                    ui.label(rf.description).classes("text-sm text-gray-700 flex-1")

        # Rationale
        if result.rationale:
            _section_hdr("RATIONALE")
            with ui.expansion("View AI rationale", icon="psychology").classes(
                "w-full border rounded"
            ):
                ui.label(result.rationale).classes("text-sm text-gray-700 whitespace-pre-wrap p-3")

        # Remediation plan
        if result.remediation:
            _section_hdr("REMEDIATION PLAN")
            for i, item in enumerate(result.remediation, 1):
                with ui.element("div").classes("flex items-start gap-3 py-1"):
                    ui.label(f"{i}.").classes("text-sm font-bold text-blue-400 w-5 shrink-0 mt-0.5")
                    ui.label(item).classes("text-sm text-gray-700 flex-1")

    def _refresh_verdict(result: AssessmentOutputModel | None = latest) -> None:
        """Clear and rebuild the verdict hero area with the given result."""
        verdict_area.clear()
        with verdict_area:
            _render_verdict_content(result)

    _refresh_verdict(latest)

    # --- Source metrics (always shown — from the release record, not the assessment) ---

    _section_hdr("SOURCE METRICS")
    sp = scope_pct(release)
    e2e = e2e_pct(release)
    sq = sq_normalized(release)
    b = release.defects_open.by_severity

    with ui.grid(columns=3).classes("w-full gap-x-6 gap-y-2 mb-3"):
        _metric_bar("Scope", sp, warn_below=0.80)
        _metric_bar("SQ Quality", sq, warn_below=0.50)
        if e2e is not None:
            _metric_bar("E2E Pass", e2e, warn_below=0.90)
        else:
            with ui.column().classes("gap-0"):
                ui.label("E2E Pass").classes("text-xs text-gray-500")
                ui.label("No data").classes("text-xs italic text-gray-400")

    # Defect row — highlighted red when blockers or multiple criticals are open.
    has_blockers = b.blocker > 0 or b.critical > 1
    defect_cls = "text-red-600 font-medium" if has_blockers else "text-gray-600"
    ui.label(
        f"Open defects: {release.defects_open.total}"
        f"  (B:{b.blocker}  C:{b.critical}  M:{b.major}  m:{b.minor})"
    ).classes(f"text-sm {defect_cls} mb-2")

    if release.weekly_last3:
        ui.label("Weekly velocity (last 3):").classes(
            "text-xs text-gray-500 font-medium uppercase tracking-wide mt-2 mb-1"
        )
        for w in release.weekly_last3:
            ui.label(f"  {w.week}:  {w.value} SP closed").classes("text-sm text-gray-600")

    if release.pv_latest:
        pv = release.pv_latest
        ratio = (pv.actual / pv.planned) if pv.planned else 0.0
        ui.label("Earned Value:").classes(
            "text-xs text-gray-500 font-medium uppercase tracking-wide mt-3 mb-1"
        )
        with ui.row().classes("items-center gap-6"):
            ui.label(f"Planned: {pv.planned:.0f} SP").classes("text-sm")
            ui.label(f"Actual:  {pv.actual:.0f} SP").classes("text-sm")
            ratio_cls = "text-green-600" if ratio >= 0.8 else "text-amber-600"
            ui.label(f"{ratio:.0%}").classes(f"text-sm font-semibold {ratio_cls}")

    # --- Environment ---
    _section_hdr("ENVIRONMENT  (shared snapshot)")
    _detail_environment(env_data)

    # --- Dependencies ---
    _section_hdr("DEPENDENCIES  (shared snapshot)")
    _detail_dependencies(dep_data)

    # --- Security ---
    _section_hdr("SECURITY  (shared snapshot)")
    _detail_security(sec_data)

    # --- Assessment history ---
    _section_hdr("ASSESSMENT HISTORY")
    history_area = ui.column().classes("w-full")

    def _render_history_content(records: list[AssessmentOutputModel]) -> None:
        """Render the history list; each row has a drill-in button for the verdict card."""
        if not records:
            with ui.element("div").classes("flex flex-col items-center gap-2 py-10 text-gray-400"):
                ui.icon("history").classes("text-5xl")
                ui.label("No assessments recorded yet.").classes("text-sm")
                ui.label("Use Run Assessment above to run the first assessment.").classes("text-xs")
            return

        for rec in records:
            # Default-arg captures the loop variable so each button opens the right record.
            def _show(r: AssessmentOutputModel = rec) -> None:
                """Open the verdict detail dialog for this history row."""
                _verdict_card(r, result_hist_col)
                result_hist_dlg.open()

            with ui.element("div").classes(
                "flex items-center justify-between w-full py-3 border-b flex-wrap gap-2"
            ):
                with ui.element("div").classes("flex flex-col gap-0"):
                    ui.label(rec.generated_at.strftime("%Y-%m-%d  %H:%M  UTC")).classes(
                        "text-xs text-gray-400"
                    )
                    ui.label(rec.release).classes("text-sm font-medium text-gray-700")
                with ui.element("div").classes("flex items-center gap-3"):
                    _verdict_chip(rec.verdict)
                    ui.label(f"{rec.score}/100").classes("text-sm font-medium text-gray-700")
                    if rec.aggregate_confidence is not None:
                        ui.label(f"{rec.aggregate_confidence:.0%} conf.").classes(
                            "text-xs text-gray-400"
                        )
                    ui.button(icon="open_in_new", on_click=_show).props("flat round").tooltip(
                        "View full verdict"
                    )

    def _refresh_history(new_out: AssessmentOutputModel | None = None) -> None:
        """Prepend new_out (if given) to hist_records, then rebuild the history area."""
        nonlocal hist_records
        if new_out is not None:
            # Deduplicate by timestamp before prepending.
            hist_records = [new_out] + [
                r for r in hist_records if r.generated_at != new_out.generated_at
            ]
        history_area.clear()
        with history_area:
            _render_history_content(hist_records)

    _refresh_history()


# ---------------------------------------------------------------------------
# Ingest panel
# ---------------------------------------------------------------------------


def _ingest_panel(config: RRRConfig, value_stream: str) -> None:
    """Render the Ingest screen: HTML report → brain JSON conversion.

    Replicates ``rrr-ingest`` in the browser so operators can ingest new weekly
    HTML reports without leaving the dashboard.  The ingest runs in a
    thread-pool executor so the event loop stays responsive during file I/O.
    """
    from nicegui import ui  # noqa: PLC0415

    brain_default = str(config.sources.brain.dir)

    ui.label("Ingest HTML Reports").classes("text-2xl font-bold text-gray-800 mb-1")
    ui.label("Convert RKT Program Metrics HTML exports to brain JSON snapshots.").classes(
        "text-sm text-gray-500 mb-5"
    )

    with ui.column().classes("gap-3 w-full max-w-xl"):
        html_input = ui.input(
            label="HTML directory",
            placeholder="./input",
        ).classes("w-full")

        brain_input = ui.input(
            label="Brain directory",
            value=brain_default,
        ).classes("w-full")

        vs_input = ui.input(
            label="Value stream",
            value=value_stream,
        ).classes("w-full")

    log_area = ui.log(max_lines=80).classes("w-full h-52 font-mono text-sm border rounded mt-2")
    log_area.push("Ready — enter the path to your HTML reports directory and click Run Ingest.")

    async def _on_run() -> None:
        """Validate inputs, run ingest in executor, stream status lines to the log."""
        html_val = html_input.value.strip()
        brain_val = brain_input.value.strip() or brain_default
        vs = vs_input.value.strip() or value_stream

        if not html_val:
            ui.notify("Enter the HTML directory path.", type="warning")
            return

        html_dir = Path(html_val)
        if not html_dir.exists():
            ui.notify(f"Directory not found: {html_dir}", type="negative")
            return

        log_area.push(f"\n→ Ingesting from {html_dir}  (value stream: {vs})")
        run_btn.disable()
        loop = asyncio.get_event_loop()
        try:
            lines: list[str] = await loop.run_in_executor(
                None,
                partial(_run_ingest_sync, html_dir, Path(brain_val), vs),
            )
        except Exception as exc:  # noqa: BLE001
            # Surface extraction errors (malformed HTML, missing __REPORT__) as
            # readable messages rather than crashing the server.
            log_area.push(f"ERROR: {exc}")
            ui.notify(f"Ingest failed: {exc}", type="negative", timeout=10000)
            run_btn.enable()
            return

        for line in lines:
            log_area.push(line)
        ui.notify("Ingest complete — navigate to Overview to see new releases.", type="positive")
        run_btn.enable()

    run_btn = ui.button("Run Ingest", icon="upload_file", on_click=_on_run).classes("mt-2")


# ---------------------------------------------------------------------------
# Collect panel (M7 Phase 2)
# ---------------------------------------------------------------------------


def _collect_panel(config: RRRConfig, navigate: Callable[..., Any]) -> None:
    """Render the Collect screen: data-freshness status grid + InputContract-driven forms.

    Two sub-views share the same inner content column (``inner[0]``):

    **Status view** — one row per registered dimension with a FRESH / STALE / MISSING
    badge, age in days, and an Edit button.  A Refresh button re-queries the file system.

    **Form view** — appears when Edit is clicked.  Introspects the dimension's
    ``InputContract`` Pydantic model and renders one NiceGUI widget per non-auto field.
    Save calls ``CollectorRunner.run()`` via ``_DictCollector`` so validation and the
    write path are shared with the ``rrr-collect`` CLI (ADR-0023).

    Intra-screen navigation (status ↔ form) is handled locally so the sidebar
    active-state highlight does not change while editing.
    """
    from nicegui import ui  # noqa: PLC0415

    # Default data directory — mirrors the CLI default (./data).
    data_dir = Path("data")
    inner: list[Any] = [None]

    def _show_status() -> None:
        """Clear the inner column and re-render the freshness status table."""
        inner[0].clear()
        with inner[0]:
            reports = collect_status_all(data_dir)
            with ui.row().classes("items-center gap-3 mb-4"):
                ui.label(f"Data directory: {data_dir.resolve()}").classes(
                    "text-sm text-gray-400"
                )
                ui.button("Refresh", icon="refresh", on_click=_show_status).props(
                    "flat dense"
                ).classes("text-xs")

            with ui.element("div").classes("w-full rounded border"):
                # Header row
                with ui.row().classes(
                    "px-4 py-2 bg-gray-100 text-xs font-semibold text-gray-500 gap-4"
                ):
                    ui.label("Dimension").classes("flex-1")
                    ui.label("Status").classes("w-36")
                    ui.label("Age").classes("w-24")
                    ui.label("").classes("w-20")  # Edit button column

                for report in reports:
                    with ui.row().classes("px-4 py-2 border-t items-center gap-4"):
                        ui.label(
                            report.dimension.replace("_", " ").title()
                        ).classes("flex-1 text-sm")

                        color = _COLLECT_STATUS_COLOR[report.status]
                        icon = _COLLECT_STATUS_ICON[report.status]
                        ui.chip(
                            report.status.value, color=color, icon=icon
                        ).props("outline dense")

                        age_str = (
                            f"{report.age_days:.1f}d"
                            if report.age_days is not None
                            else "—"
                        )
                        ui.label(age_str).classes("w-24 text-sm text-gray-500")

                        ui.button(
                            "Edit",
                            on_click=lambda d=report.dimension: _show_form(d),
                        ).props("flat dense color=primary").classes("w-20 text-xs")

    def _show_form(dimension: str) -> None:
        """Replace the inner column with the InputContract form for one dimension."""
        inner[0].clear()
        registry = CollectorRegistry()
        model_class = registry.model_for(dimension)
        existing = load_collect_form_data(data_dir, dimension)

        with inner[0]:
            ui.button("← Status", on_click=_show_status).props("flat dense").classes("mb-2")
            ui.label(dimension.replace("_", " ").title()).classes(
                "text-xl font-semibold text-gray-800 mb-4"
            )

            release_input = ui.input(
                label="Release name",
                value=existing.get("release", ""),
                placeholder="Enter the IR name",
            ).classes("w-full max-w-xl mb-2")

            # field_refs maps field_name → bound widget for save-time reading.
            field_refs: dict[str, Any] = {}
            with ui.column().classes("gap-3 w-full max-w-xl"):
                for name, field_info in model_class.model_fields.items():
                    if name in _AUTO_FIELDS:
                        continue
                    inner_type, _ = _unwrap_collect_optional(field_info.annotation)
                    existing_val = existing.get(name)
                    widget = _build_collect_field_widget(
                        name, field_info, inner_type, existing_val
                    )
                    if widget is not None:
                        field_refs[name] = widget

            async def _on_save() -> None:
                """Validate and write the form data via CollectorRunner.run()."""
                form_data: dict[str, Any] = {
                    "schema_version": "1.0.0",
                    "release": release_input.value,
                }
                for fname, widget in field_refs.items():
                    form_data[fname] = widget.value

                runner = CollectorRunner()
                col_cfg = CollectorConfig(release=release_input.value, data_dir=data_dir)
                try:
                    result = runner.run(
                        dimension,
                        _DictCollector(dimension, form_data),
                        col_cfg,
                        model_class,
                    )
                except Exception as exc:  # noqa: BLE001
                    # Pydantic ValidationError or write failure — surface as a UI notification.
                    ui.notify(f"Save failed: {exc}", type="negative", timeout=10000)
                    return
                ui.notify(
                    f"Saved {dimension}.json (captured_at: {result.collected_at})",
                    type="positive",
                )
                _show_status()

            ui.button("Save", icon="save", on_click=_on_save).props(
                "color=primary"
            ).classes("mt-4")

    ui.label("Collect Dimension Data").classes("text-2xl font-bold text-gray-800 mb-1")
    ui.label(
        "Capture supplementary dimension JSON files before running rrr --release."
    ).classes("text-sm text-gray-500 mb-5")

    col = ui.column().classes("w-full")
    inner[0] = col
    _show_status()


# ---------------------------------------------------------------------------
# History panel
# ---------------------------------------------------------------------------


def _history_panel(config: RRRConfig, value_stream: str) -> None:
    """Render the History screen: programme filter + TOC VS filter + assessments from SQLite.

    Loads all recent assessments from SQLite, cross-references each record's
    release name against the current brain snapshot to tag it with its
    ``toc_value_stream`` and ``programme``.

    A programme filter row (one button per engineering team) narrows the record
    pool first.  A TOC VS filter then narrows within the programme-filtered pool.
    Both filters rebuild from the same ``_rebuild_panel()`` closure so they stay
    consistent (ADR-0022).  Clicking any row opens the full verdict detail dialog.
    """
    from nicegui import ui  # noqa: PLC0415

    ui.label("Assessment History").classes("text-2xl font-bold text-gray-800 mb-1")
    ui.label("Recent assessments across all releases.").classes("text-sm text-gray-500 mb-5")

    store = AssessmentStore(config.memory.sqlite_path)
    try:
        records = store.all_recent(value_stream=value_stream, limit=50)
    finally:
        store.close()

    # Shared detail dialog — populated on row click.
    detail_col: Any = None
    with ui.dialog().props("full-width") as detail_dlg, ui.card().classes("w-full max-w-2xl p-6"):
        with ui.column().classes("w-full gap-4"):
            detail_col = ui.column().classes("w-full")
            ui.button("Close", icon="close", on_click=detail_dlg.close).classes("self-end")

    if not records:
        with ui.column().classes("items-center gap-2 py-12 text-gray-400"):
            ui.icon("history").classes("text-5xl")
            ui.label("No assessments recorded yet.").classes("text-base")
            ui.label("Run an assessment from the Overview tab to see results here.").classes(
                "text-sm"
            )
        return

    # Build lookups from brain snapshot to tag each history record.
    brain_releases = load_releases(config, value_stream)
    vs_lookup: dict[str, str | None] = {r.ir_name: r.toc_value_stream for r in brain_releases}
    prog_lookup: dict[str, str | None] = {r.ir_name: r.programme for r in brain_releases}

    # Records container — cleared and rebuilt when either filter changes.
    records_col = ui.column().classes("w-full gap-2 mt-2")

    def _render_records(group_records: list[AssessmentOutputModel]) -> None:
        """Clear and rebuild the history card list for the given record subset."""
        records_col.clear()
        with records_col:
            if not group_records:
                ui.label("No assessments in this filter.").classes("text-gray-400 italic py-4")
                return
            for rec in group_records:
                # Default-arg captures loop variable so each button opens the right record.
                def _show(r: AssessmentOutputModel = rec) -> None:
                    """Open the verdict detail dialog for a history row."""
                    _verdict_card(r, detail_col)
                    detail_dlg.open()

                with ui.card().classes("w-full"):
                    with ui.row().classes("items-center justify-between w-full flex-wrap gap-2"):
                        with ui.column().classes("gap-0"):
                            ui.label(rec.release).classes("font-semibold")
                            ui.label(rec.generated_at.strftime("%Y-%m-%d  %H:%M  UTC")).classes(
                                "text-xs text-gray-400"
                            )

                        with ui.row().classes("items-center gap-3"):
                            _verdict_chip(rec.verdict)
                            ui.label(f"{rec.score}/100").classes(
                                "text-sm font-medium w-14 text-right"
                            )
                            if rec.aggregate_confidence is not None:
                                ui.label(f"{rec.aggregate_confidence:.0%} conf.").classes(
                                    "text-xs text-gray-400"
                                )
                            ui.button(icon="open_in_new", on_click=_show).props(
                                "flat round"
                            ).tooltip("View details")

    # VS-filter + records container — rebuilt when the programme filter changes.
    vs_section = ui.column().classes("w-full")

    def _rebuild_panel(pool_records: list[AssessmentOutputModel]) -> None:
        """Rebuild the TOC VS filter row and record list for the given pool."""
        vs_section.clear()
        with vs_section:
            # Group the pool by TOC VS using the brain lookup.
            hist_groups: dict[str, list[AssessmentOutputModel]] = {"All": list(pool_records)}
            for rec in pool_records:
                bucket = vs_lookup.get(rec.release) or "Untagged"
                hist_groups.setdefault(bucket, []).append(rec)

            _special = {"All", "Untagged"}
            vs_sorted = sorted(k for k in hist_groups if k not in _special)
            visible_keys = ["All"] + vs_sorted + (["Untagged"] if "Untagged" in hist_groups else [])
            show_vs_filter = bool(vs_sorted) and len(visible_keys) > 1

            if show_vs_filter:
                ui.label("Filter by value stream:").classes(
                    "text-xs text-gray-500 font-medium uppercase tracking-wide mb-1"
                )
                with ui.row().classes("gap-2 flex-wrap mb-2"):
                    for key in visible_keys:
                        count = len(hist_groups[key])
                        color = _TRENDS_SPECIAL_COLOR.get(key, "primary")
                        ui.button(
                            f"{key}  ({count})",
                            color=color,
                            on_click=lambda k=key: _render_records(hist_groups[k]),
                        ).props("outline").classes("text-xs")

        _render_records(pool_records)

    # Programme filter — cross-reference history records via prog_lookup.
    all_programmes = sorted({prog for prog in prog_lookup.values() if prog})
    if len(all_programmes) > 1:
        prog_pools: dict[str, list[AssessmentOutputModel]] = {"All": list(records)}
        for rec in records:
            p = prog_lookup.get(rec.release) or "Unknown"
            prog_pools.setdefault(p, []).append(rec)

        visible_progs = ["All"] + sorted(prog_pools.keys() - {"All"})
        ui.label("Programme:").classes(
            "text-xs text-gray-500 font-medium uppercase tracking-wide mb-1"
        )
        with ui.row().classes("gap-2 flex-wrap mb-3"):
            for prog in visible_progs:
                count = len(prog_pools.get(prog, []))
                color = "teal" if prog != "All" else "blue-grey"
                ui.button(
                    f"{prog}  ({count})",
                    color=color,
                    on_click=lambda p=prog: _rebuild_panel(prog_pools[p]),
                ).props("outline").classes("text-xs")

    _rebuild_panel(list(records))


# ---------------------------------------------------------------------------
# Trends panel
# ---------------------------------------------------------------------------


def _trends_panel(config: RRRConfig, value_stream: str) -> None:
    """Render the Trends screen: programme filter + TOC VS filter + score-over-time chart.

    Scores are computed from brain snapshot history (one data point per weekly
    HTML ingest) using ``score_over_snapshots()``, so the chart shows how the
    release's readiness evolved across the weekly HTML ingests, independently of
    whether the user ever ran a manual assessment.

    Selection model (ADR-0022): programme filter narrows the pool; TOC VS filter
    then narrows within the programme pool; the release selector picks from the
    TOC-filtered subset.  Clicking a programme button rebuilds both the TOC VS
    filter row and the release selector via ``_rebuild_all()``.

    The chart is rendered via ``ui.echart`` (Apache ECharts) with GO/NO_GO
    threshold lines.
    """
    from nicegui import ui  # noqa: PLC0415

    ui.label("Trends").classes("text-2xl font-bold text-gray-800 mb-1")
    ui.label("Score over time by release — computed from weekly brain snapshots.").classes(
        "text-sm text-gray-500 mb-5"
    )

    all_records = load_releases(config, value_stream)

    if not all_records:
        with ui.column().classes("items-center gap-2 py-12 text-gray-400"):
            ui.icon("trending_up").classes("text-5xl")
            ui.label("No brain data found.").classes("text-base")
            ui.label("Use the Ingest screen to load RKT HTML reports first.").classes("text-sm")
        return

    def _make_toc_groups(pool: list[ReleaseRecord]) -> dict[str, list[ReleaseRecord]]:
        """Build {All: ..., <VS name>: ..., Untagged: ...} for a release pool."""
        groups: dict[str, list[ReleaseRecord]] = {"All": pool}
        for r in pool:
            bucket = r.toc_value_stream if r.toc_value_stream is not None else "Untagged"
            groups.setdefault(bucket, []).append(r)
        return groups

    def _make_options(records: list[ReleaseRecord]) -> dict[str, str]:
        """Build ir_name → display-label dict for ui.select.

        NiceGUI dict-based select uses KEYS as the internal value (returned by
        ``e.value`` in ``on_change``) and VALUES as the displayed label.  The
        ``[PROG]`` prefix on each label lets users search by programme code
        (e.g. "OSM") in filterable mode.
        """
        return {r.ir_name: f"[{r.programme}]  {r.ir_name}" for r in records}

    # Chart area — rebuilt on each selection change.
    chart_col = ui.column().classes("w-full gap-4 mt-4")

    def _render_chart(release_name: str) -> None:
        """Clear the chart area and draw the score-over-snapshot echart for release_name."""
        chart_col.clear()
        with chart_col:
            ui.spinner(size="lg").classes("mx-auto my-8")

        async def _compute() -> None:
            """Score the release across all brain snapshots and render the ECharts line."""
            loop = asyncio.get_event_loop()
            dates, scores = await loop.run_in_executor(
                None,
                partial(score_over_snapshots, config, release_name, value_stream),
            )
            chart_col.clear()
            with chart_col:
                if len(scores) < 2:
                    ui.label(
                        f"Only {len(scores)} snapshot(s) found for this release — "
                        "ingest more weekly HTML reports to see a trend."
                    ).classes("text-gray-400 italic py-4")
                    return

                # Line colour reflects final snapshot score: green GO, amber CONDITIONAL, red NO_GO.
                last = scores[-1]
                line_color = "#22c55e" if last >= 80 else "#f59e0b" if last >= 40 else "#ef4444"
                ui.echart(
                    {
                        "title": {
                            "text": f"Readiness — {release_name}",
                            "left": "center",
                            "textStyle": {"fontSize": 13},
                        },
                        "tooltip": {"trigger": "axis"},
                        "xAxis": {
                            "type": "category",
                            "data": dates,
                            "axisLabel": {"rotate": 30},
                        },
                        "yAxis": {
                            "type": "value",
                            "min": 0,
                            "max": 100,
                            "axisLabel": {"formatter": "{value}"},
                        },
                        "series": [
                            {
                                "name": "Score",
                                "type": "line",
                                "data": scores,
                                "smooth": True,
                                "symbol": "circle",
                                "symbolSize": 6,
                                "itemStyle": {"color": line_color},
                                "lineStyle": {"color": line_color, "width": 2},
                                # Horizontal threshold lines at GO (80) and NO_GO (40) score bands.
                                "markLine": {
                                    "silent": True,
                                    "lineStyle": {"type": "dashed", "opacity": 0.5},
                                    "data": [
                                        {"yAxis": 80, "name": "GO", "label": {"formatter": "GO"}},
                                        {
                                            "yAxis": 40,
                                            "name": "NO_GO",
                                            "label": {"formatter": "NO_GO"},
                                        },
                                    ],
                                },
                            }
                        ],
                        "grid": {
                            "left": "5%",
                            "right": "5%",
                            "bottom": "15%",
                            "containLabel": True,
                        },
                    }
                ).classes("w-full h-72")

        asyncio.ensure_future(_compute())

    # Selector container — cleared and rebuilt when either filter changes.
    selector_col = ui.column().classes("w-full max-w-2xl gap-2")

    def _rebuild_selector(records: list[ReleaseRecord]) -> None:
        """Repopulate the release selector with the given record subset."""
        selector_col.clear()
        options = _make_options(records)
        if not options:
            with selector_col:
                ui.label("No releases in this filter.").classes("text-gray-400 italic")
            return
        # options keys are ir_names (the internal value); pick the first as the default.
        first_ir = next(iter(options.keys()))
        with selector_col:
            ui.select(
                options,
                value=first_ir,
                label=f"Release — {len(records)} shown  (type to filter by name or [PROG])",
                on_change=lambda e: _render_chart(e.value),
            ).props("filterable use-input input-debounce=0").classes("w-full")
        _render_chart(first_ir)

    # TOC filter section — cleared and rebuilt when the programme filter changes.
    toc_filter_col = ui.column().classes("w-full")

    # Mutable refs track the active selection so buttons re-render with the correct style.
    _sel_vs: list[str] = ["All"]
    _sel_prog: list[str] = ["All"]

    def _draw_toc_filter(pool: list[ReleaseRecord]) -> None:
        """Redraw TOC VS filter buttons using current _sel_vs[0] for active styling.

        Separated from _rebuild_all so a VS-button click can refresh button styles
        without resetting _sel_vs to "All" the way a programme-switch does.
        """
        toc_groups = _make_toc_groups(pool)
        _special = {"All", "Untagged"}
        toc_vs_sorted = sorted(k for k in toc_groups if k not in _special)
        visible_keys = ["All"] + toc_vs_sorted + (["Untagged"] if "Untagged" in toc_groups else [])
        show_toc_filter = bool(toc_vs_sorted) and len(visible_keys) > 1

        toc_filter_col.clear()
        with toc_filter_col:
            if show_toc_filter:
                ui.label("Filter by value stream:").classes(
                    "text-xs text-gray-500 font-medium uppercase tracking-wide mb-1"
                )
                with ui.row().classes("gap-2 flex-wrap"):
                    for key in visible_keys:
                        count = len(toc_groups[key])
                        color = _TRENDS_SPECIAL_COLOR.get(key, "primary")
                        # Filled style for the active selection, outlined for the rest.
                        btn_props = "unelevated" if key == _sel_vs[0] else "outline"

                        def _on_vs_click(
                            k: str = key,
                            g: dict[str, list[ReleaseRecord]] = toc_groups,
                            p: list[ReleaseRecord] = pool,
                        ) -> None:
                            """Set VS selection, refresh button styles, rebuild selector."""
                            _sel_vs[0] = k
                            _draw_toc_filter(p)
                            _rebuild_selector(g[k])

                        ui.button(
                            f"{key}  ({count})",
                            color=color,
                            on_click=_on_vs_click,
                        ).props(btn_props).classes("text-xs")

    def _rebuild_all(pool: list[ReleaseRecord]) -> None:
        """Reset VS filter to All, redraw VS buttons and selector for the given pool."""
        _sel_vs[0] = "All"
        _draw_toc_filter(pool)
        _rebuild_selector(pool)

    # Programme filter row — only shown when releases span multiple teams.
    programmes = list_programmes(all_records)
    prog_filter_col = ui.column().classes("w-full")

    if programmes:
        prog_pools: dict[str, list[ReleaseRecord]] = {"All": all_records}
        for r in all_records:
            prog_pools.setdefault(r.programme or "Unknown", []).append(r)

        def _render_prog_buttons() -> None:
            """Redraw programme filter buttons with filled style on the active one."""
            prog_filter_col.clear()
            with prog_filter_col:
                ui.label("Programme:").classes(
                    "text-xs text-gray-500 font-medium uppercase tracking-wide mb-1"
                )
                with ui.row().classes("gap-2 flex-wrap mb-3"):
                    for prog in ["All"] + programmes:
                        count = len(prog_pools[prog])
                        color = "teal" if prog != "All" else "blue-grey"
                        btn_props = "unelevated" if prog == _sel_prog[0] else "outline"

                        def _on_prog_click(p: str = prog) -> None:
                            """Switch programme: update selection, redraw both filter rows."""
                            _sel_prog[0] = p
                            _rebuild_all(prog_pools[p])
                            _render_prog_buttons()

                        ui.button(
                            f"{prog}  ({count})",
                            color=color,
                            on_click=_on_prog_click,
                        ).props(btn_props).classes("text-xs")

        _render_prog_buttons()

    _rebuild_all(all_records)


# ---------------------------------------------------------------------------
# Page registration and server start
# ---------------------------------------------------------------------------


def register_pages(config: RRRConfig, all_datasets: list[str]) -> None:
    """Register all NiceGUI URL routes (must be called before ``ui.run()``).

    Accepts a list of dataset labels (brain file stems) discovered by
    ``list_datasets()``.  The active dataset is resolved from the ``?dataset=``
    query parameter on each page request; when absent, the first label in
    ``all_datasets`` is used.

    The main page uses a persistent left sidebar for navigation (Overview /
    History / Trends / Ingest).  Clicking a sidebar item swaps the content area
    in place — only the ``?dataset=`` switch triggers a full page reload.
    When more than one dataset is available, a ``ui.select`` picker appears in
    the header.
    """
    from nicegui import ui  # noqa: PLC0415

    default_vs = all_datasets[0] if all_datasets else config.sources.brain.value_stream

    @ui.page("/")
    async def index(dataset: str | None = None) -> None:
        """Main dashboard — sidebar navigation with Overview, History, Trends, Ingest, Collect."""
        vs = dataset if (dataset and dataset in all_datasets) else default_vs

        # Pre-load shared data once per browser page load.
        all_releases = load_releases(config, vs)
        env_data = load_environment(config)
        dep_data = load_dependency(config)
        sec_data = load_security_data(config)

        # Mutable references let _navigate rebuild the drawer and content area.
        drawer_inner: list[Any] = [None]
        content_ref: list[Any] = [None]

        # --- Define navigation functions before creating any UI elements ---

        def _build_sidebar(active: str) -> None:
            """Render sidebar nav items with the correct active-state highlighting."""
            from nicegui import ui as _ui  # noqa: PLC0415

            main_items = [
                ("overview", "dashboard", "Overview"),
                ("history", "history", "History"),
                ("trends", "trending_up", "Trends"),
            ]
            admin_items = [
                ("ingest", "upload_file", "Ingest"),
                ("collect", "cloud_download", "Collect"),
            ]
            # Overview and Detail share the same sidebar highlight.
            for view_key, icon_name, label in main_items:
                is_active = view_key == active or (view_key == "overview" and active == "detail")
                _nav_item(view_key, icon_name, label, is_active, _navigate)
            # Separator visually separates the admin Ingest item.
            _ui.separator().classes("my-1 mx-3")
            for view_key, icon_name, label in admin_items:
                _nav_item(view_key, icon_name, label, view_key == active, _navigate)

        def _render_view(view: str, release: ReleaseRecord | None = None) -> None:
            """Dispatch to the correct screen function for the given view key."""
            if view == "overview":
                _overview_panel(all_releases, config, vs, _navigate)
            elif view == "detail" and release is not None:
                store = AssessmentStore(config.memory.sqlite_path)
                try:
                    latest = latest_for_release(store, release.ir_name, vs)
                    hist_recs = store.history(release.ir_name, vs, limit=20)
                finally:
                    store.close()
                _release_detail(
                    release,
                    config,
                    vs,
                    env_data,
                    dep_data,
                    sec_data,
                    latest,
                    hist_recs,
                    _navigate,
                )
            elif view == "history":
                _history_panel(config, vs)
            elif view == "trends":
                _trends_panel(config, vs)
            elif view == "ingest":
                _ingest_panel(config, vs)
            elif view == "collect":
                _collect_panel(config, _navigate)

        def _navigate(view: str, release: ReleaseRecord | None = None) -> None:
            """Update the sidebar active state and swap the content area."""
            if drawer_inner[0] is not None:
                drawer_inner[0].clear()
                with drawer_inner[0]:
                    _build_sidebar(view)
            if content_ref[0] is not None:
                content_ref[0].clear()
                with content_ref[0]:
                    _render_view(view, release)

        # --- Create UI elements ---

        with (
            ui.header().classes("bg-white border-b shadow-sm items-center").style("min-height:56px")
        ):
            with ui.element("div").classes("flex items-center gap-3 px-4 w-full h-full"):
                ui.icon("assessment").classes("text-blue-700 text-2xl shrink-0")
                ui.label("Release Readiness").classes("text-lg font-semibold text-gray-800")
                ui.element("div").classes("flex-1")
                if len(all_datasets) > 1:
                    # Switching dataset reloads the page so all brain data resets.
                    ui.select(
                        {d: d for d in all_datasets},
                        value=vs,
                        label="Dataset",
                        on_change=lambda e: ui.navigate.to(f"/?dataset={e.value}"),
                    ).classes("min-w-[10rem]").props("dense outlined")
                else:
                    ui.label(vs).classes("text-sm text-gray-400")

        with (
            ui.left_drawer(value=True, fixed=True)
            .props("width=140 bordered")
            .classes("bg-gray-50 pt-3")
        ):
            dc = ui.column().classes("w-full gap-1 px-1")
            drawer_inner[0] = dc
            with dc:
                _build_sidebar("overview")

        # Main content area — rendered after the drawer so it occupies the remaining width.
        content = ui.column().classes("w-full p-6")
        content_ref[0] = content

        with content:
            _render_view("overview")


def _setup_basic_auth(username: str, password: str) -> None:
    """Install HTTP Basic Auth ASGI middleware on the NiceGUI FastAPI app (T-02).

    Must be called before ``ui.run()`` — NiceGUI's FastAPI ``app`` object is
    populated at import time, so middleware added here is in place for every
    request including the WebSocket handshake and NiceGUI's internal ``/_nicegui``
    paths.  The ``WWW-Authenticate: Basic`` header triggers the browser's built-in
    credential dialog on first access.

    Args:
        username: Required username for HTTP Basic Auth.
        password: Required password for HTTP Basic Auth.
    """
    import base64  # noqa: PLC0415

    from nicegui import app as nicegui_app  # noqa: PLC0415
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: PLC0415
    from starlette.requests import Request  # noqa: PLC0415
    from starlette.responses import Response  # noqa: PLC0415

    # Pre-encode the expected credentials once; comparison is O(1) per request.
    expected = base64.b64encode(f"{username}:{password}".encode()).decode()

    class _BasicAuth(BaseHTTPMiddleware):
        """Middleware that challenges unauthenticated requests with 401."""

        async def dispatch(self, request: Request, call_next: Any) -> Any:
            """Allow requests with valid Basic credentials; return 401 otherwise."""
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Basic ") and auth[6:] == expected:
                return await call_next(request)
            return Response(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="RRR Dashboard"'},
            )

    nicegui_app.add_middleware(_BasicAuth)


def run_ui(
    config: RRRConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    show: bool = True,
) -> None:
    """Register pages and start the NiceGUI server (blocks until Ctrl-C / SIGTERM).

    Auto-scans ``brain/*-history.json`` via ``list_datasets()`` to discover
    available datasets.  When exactly one file is found it is used without any
    CLI argument.  When multiple files exist, a dataset picker appears in the
    page header (ADR-0022).

    When ``config.ui.auth_user`` is set, installs HTTP Basic Auth middleware
    before starting the server (T-02, ADR-0020).

    Binds to ``127.0.0.1`` by default so the dashboard is not reachable from
    other machines (local-first, ADR-0010).  Pass ``show=False`` to suppress the
    automatic browser-open (useful in headless environments).

    Args:
        config: Validated ``RRRConfig`` from ``ConfigLoader.load()``.
        host: Network interface to bind (default ``127.0.0.1``).
        port: TCP port for the HTTP server (default 8080).
        show: Whether to open a browser tab automatically on startup.
    """
    from nicegui import ui  # noqa: PLC0415

    # Install auth middleware before registering pages so it covers all routes.
    if config.ui.auth_user is not None and config.ui.auth_password is not None:
        _setup_basic_auth(config.ui.auth_user, config.ui.auth_password)

    all_datasets = list_datasets(config)
    if not all_datasets:
        # brain/ is empty or missing — use the config default as a fallback so
        # the server starts and shows the Ingest screen rather than crashing.
        all_datasets = [config.sources.brain.value_stream]

    register_pages(config, all_datasets)
    ui.run(
        title="RRR Dashboard",
        host=host,
        port=port,
        reload=False,
        show=show,
    )
