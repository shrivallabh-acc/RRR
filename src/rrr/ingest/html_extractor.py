"""Extract RKT Program Metrics HTML into brain-contract release dicts (ADR-0018).

The HTML embeds all data in a single JSON literal ``const __REPORT__ = {...}`` — we
extract that with a regex and map each release to the shape ``RKTBrainReader`` expects.
The HTML DOM is never parsed; only the machine-readable JSON literal and the TOC
section matter.

Field mapping summary (full rationale in ADR-0018, ADR-0021):
  summary, ir_name       — direct copy of matching keys
  programme              — extracted from ir_name prefix/suffix (AIMS/PIMS/R5/…); "OSM" if untagged
  release_relationship   — parsed from "(Dependency for: X; Launch: Y)" in ir_name; null if absent
  toc_value_stream       — business VS name from TOC slide (ADR-0021); null if absent from TOC
  pv_latest              — last element of pv.{pv,actual} series
  sq_avg / sq_below_1    — sq_caps scores converted from 0-2 to 0-3 scale (× 1.5)
  defect_trend_last5     — running cumulative open defects, last 5 data points
  defects_open           — defect_priority matrix summed by column (priority label)
  defects_closed_cumul.  — sum of defects_closed daily values
  e2e_latest             — e2e_overall last entry (real counts, not percentages); null if absent
  weekly_last3           — last 3 entries of the weekly story-point velocity series
"""

from __future__ import annotations

import html as _html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Regex that matches the single __REPORT__ literal anywhere on a line.
_REPORT_RE = re.compile(r"const __REPORT__\s*=\s*(\{.+\})\s*;?\s*$")

# Captures the TOC slide content up to (but not including) the next page div.
# The TOC slide carries data-ribbon="Table of Contents" on its page wrapper.
_TOC_SLIDE_RE = re.compile(
    r'data-ribbon="Table of Contents"(.*?)(?=<div class="page")',
    re.DOTALL,
)
# Matches the value-stream label element inside the TOC.
_TOC_VS_RE = re.compile(r'class="toc-vs-label"[^>]*>([^<]+)<')
# Matches one release link inside a toc-releases list.
_TOC_REL_RE = re.compile(r"<li><a\s+href=[^>]+>([^<]+)</a></li>")
# Used by _normalize_name to collapse runs of whitespace.
_SPACE_RE = re.compile(r"\s+")

# HTML score threshold below which a capability is flagged as quality risk.
# HTML sq_caps.scores are on a 0-2 scale; the brain contract stores sq_avg on 0-3
# (multiplied by 1.5). A raw HTML score of 2/3 maps to 1.0 on the 0-3 brain scale,
# which is the "below 1" risk gate in the TestReadiness assessor.
_SQ_RISK_THRESHOLD = 2.0 / 3.0

# Maps HTML defect priority labels to brain contract severity keys.
_PRIORITY_MAP: dict[str, str] = {
    "Blocker": "blocker",
    "Critical": "critical",
    "Major": "major",
    "Minor": "minor",
}

# Programme-code patterns matched against ir_name (prefix or suffix).
# The RKT HTML has no separate programme field — all grouping is encoded in the
# release name string. Patterns are tried in order; first match wins.
# Releases with no match are native to the current value stream (default "OSM").
_PROGRAMME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^AIMS\s*[-–]\s*", re.IGNORECASE), "AIMS"),
    (re.compile(r"^PIMS\s*[-–]\s*", re.IGNORECASE), "PIMS"),
    (re.compile(r"^EIMS\s*[-–]\s*", re.IGNORECASE), "EIMS"),
    # R5 / R6 are release-generation prefixes, not programme codes per se, but
    # they group releases that are NOT native to the current value stream.
    (re.compile(r"^R5\s+", re.IGNORECASE), "R5"),
    (re.compile(r"^R6\s+", re.IGNORECASE), "R6"),
    # Suffix markers — present in parentheses at the end of the release name.
    (re.compile(r"\(ME&Q\)", re.IGNORECASE), "ME&Q"),
    (re.compile(r"\(NEO\)", re.IGNORECASE), "NEO"),
    # Embedded marker — no consistent position.
    (re.compile(r"\bR@W\b"), "R@W"),
]

# Matches the structured enabler annotation inside ir_name:
#   "... (Dependency for: DIST; Launch: Terminations Cash Withdrawals)"
# Group 1 = target programme/label, Group 2 = downstream release name.
# The inner release name may itself contain parentheses (e.g. "(Adopt & Manage)"),
# so we match up to the final closing paren on the string rather than the first.
_DEPENDENCY_RE = re.compile(
    r"\(Dependency for:\s*([^;]+);\s*Launch:\s*(.+)\)\s*$",
    re.IGNORECASE,
)


class HTMLExtractor:
    """Reads one RKT Program Metrics HTML file and maps its releases to the brain contract."""

    def extract(self, html_path: Path) -> tuple[str, list[dict[str, Any]]]:
        """Parse *html_path* and return ``(snapshot_date, [release_dict, ...])``.

        *snapshot_date* is ISO-8601 (e.g. ``"2026-06-19"``), derived from the
        ``generated`` timestamp embedded in ``__REPORT__``.  Each release dict
        matches the schema expected by ``RKTBrainReader`` (docs/brain-schema.md),
        including ``toc_value_stream`` populated from the TOC slide (ADR-0021).

        Raises ``ValueError`` if ``__REPORT__`` cannot be found or parsed.
        """
        text = html_path.read_text(encoding="utf-8", errors="replace")
        report = self._parse_report(text)
        date = _parse_generated(report["generated"])
        toc_vs_map = _parse_toc(text)
        releases = [_map_release(r, toc_vs_map) for r in report.get("releases", [])]
        return date, releases

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_report(html: str) -> dict[str, Any]:
        """Locate and JSON-parse the ``__REPORT__`` literal in the HTML source.

        Scans line by line so the regex stays simple; the literal is always on
        one line in practice (~line 270 of a 2.3 MB report).
        """
        for line in html.splitlines():
            m = _REPORT_RE.search(line)
            if m:
                return json.loads(m.group(1))  # type: ignore[no-any-return]
        raise ValueError(
            "Could not find 'const __REPORT__ = {...}' in the HTML file. "
            "The file may not be a valid RKT Program Metrics report."
        )


# ---------------------------------------------------------------------------
# Module-level mapping helpers (pure functions, no state)
# ---------------------------------------------------------------------------


def _parse_generated(generated: str) -> str:
    """Convert 'June 19, 2026 05:57 AM EST' to '2026-06-19'.

    Only the date portion is needed; the time and timezone are discarded.
    """
    m = re.match(r"(\w+ \d+, \d{4})", generated)
    if not m:
        raise ValueError(f"Cannot parse generated date: {generated!r}")
    return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")


def _map_release(
    r: dict[str, Any],
    toc_vs_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map one raw ``__REPORT__`` release entry to the brain contract shape.

    ``toc_vs_map`` is the optional ``{normalized_ir_name: vs_name}`` dict built
    by ``_parse_toc()``.  When supplied, the release's ``toc_value_stream`` is
    set from the map lookup; ``None`` means the release did not appear in the TOC
    or no TOC was found in the HTML (ADR-0021).
    """
    ir_name: str = r["ir_name"]
    toc_vs: str | None = None
    if toc_vs_map:
        toc_vs = toc_vs_map.get(_normalize_name(ir_name))
    result: dict[str, Any] = {
        "ir_name": ir_name,
        "programme": _extract_programme(ir_name),
        "toc_value_stream": toc_vs,
        "summary": _summary(r.get("summary", {})),
        "weekly_last3": _weekly_last3(r.get("weekly", {})),
        "pv_latest": _pv_latest(r.get("pv", {})),
        "sq_avg": _sq_avg(r.get("sq_caps", {})),
        "sq_below_1": _sq_below_1(r.get("sq_caps", {})),
        "defect_trend_last5": _defect_trend_last5(r.get("defect_trend", {})),
        "defects_open": _defects_open(r.get("defect_priority", {})),
        "defects_closed_cumulative": sum(r.get("defects_closed", {}).get("values", [])),
        "e2e_latest": _e2e_latest(r.get("e2e_overall", {})),
    }
    relationship = _extract_relationship(ir_name)
    if relationship is not None:
        result["release_relationship"] = relationship
    return result


def _summary(s: dict[str, Any]) -> dict[str, Any]:
    """Extract the four brain-contract summary fields from the raw summary block."""
    return {
        "total": s.get("total", 0),
        "closed": s.get("closed", 0),
        "remaining": s.get("remaining", 0),
        "pct": s.get("pct", 0),
    }


def _weekly_last3(weekly: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the last 3 weekly velocity data points as ``[{week, value}, ...]``.

    Fewer than 3 entries are returned as-is for releases early in their lifecycle.
    Entries with a null value are skipped — the RKT report pads future weeks with null.
    """
    labels: list[str] = weekly.get("labels", [])
    values: list[Any] = weekly.get("values", [])
    return [
        {"week": w, "value": int(v)} for w, v in zip(labels, values, strict=False) if v is not None
    ][-3:]


def _pv_latest(pv: dict[str, Any]) -> dict[str, Any]:
    """Extract the latest planned-value point from the daily PV time series.

    ``pv.pv`` is the planned-value (S-curve budget) series; ``pv.actual`` is the
    actual story-point burn. Taking the last non-null element gives the most recent
    reading. The RKT report extends both series to the planned end date, padding
    future entries with null — these must be filtered before indexing.
    """
    pv_series: list[Any] = pv.get("pv", [])
    actual_series: list[Any] = pv.get("actual", [])
    # Strip nulls — future dates in the series have no reported values yet.
    pv_vals = [v for v in pv_series if v is not None]
    actual_vals = [v for v in actual_series if v is not None]
    return {
        "planned": int(pv_vals[-1]) if pv_vals else 0,
        "actual": int(actual_vals[-1]) if actual_vals else 0,
    }


def _sq_avg(sq_caps: dict[str, Any]) -> float:
    """Convert capability quality scores (0–1 HTML scale) to the brain 0–3 scale.

    The brain contract stores sq_avg on 0–3 so that the assessor formula
    ``quality = sq_avg / 3`` produces a 0–1 sub-score without extra conversion.
    An empty sq_caps or all-null scores (release has no quality data) returns 0.0.
    """
    scores: list[Any] = sq_caps.get("scores", [])
    valid: list[float] = [float(s) for s in scores if s is not None]
    if not valid:
        return 0.0
    # HTML scores are on a 0-2 scale; multiply by 1.5 to convert to the brain 0-3 scale.
    # Clamp at 3.0 for the rare case where individual scores exceed 2.0.
    return min(round(sum(valid) / len(valid) * 1.5, 4), 3.0)


def _sq_below_1(sq_caps: dict[str, Any]) -> list[str]:
    """Return capability names whose score falls below 1.0 on the 0–3 brain scale.

    On the HTML 0–1 scale that threshold is 1/3 ≈ 0.333 — capabilities this low
    are flagged as quality risks in the TestReadiness assessor.
    Null scores are skipped (treated as absent, not as zero risk).
    """
    names: list[str] = sq_caps.get("names", [])
    scores: list[Any] = sq_caps.get("scores", [])
    return [
        n for n, s in zip(names, scores, strict=False) if s is not None and s < _SQ_RISK_THRESHOLD
    ]


def _defect_trend_last5(defect_trend: dict[str, Any]) -> list[int]:
    """Derive last-5 running-open-defect counts from the daily created/resolved deltas.

    The assessor classifies trend direction (declining/flat/rising) from this series.
    Running total can never go below zero — a burst of resolutions cannot produce
    negative open counts. Null entries are treated as zero (no activity that day).
    """
    created: list[Any] = defect_trend.get("created", [])
    resolved: list[Any] = defect_trend.get("resolved", [])
    running: list[int] = []
    open_count = 0
    for c, r in zip(created, resolved, strict=False):
        # Null means no data reported for that day — treat as zero activity.
        open_count = max(0, open_count + (c or 0) - (r or 0))
        running.append(open_count)
    return running[-5:]


def _defects_open(defect_priority: dict[str, Any]) -> dict[str, Any]:
    """Build the brain ``defects_open`` block from the priority matrix.

    The HTML stores a matrix where each key is an active status (e.g. 'In Dev')
    and each value is an array indexed by the ``labels`` list of priority names.
    We sum across all statuses for each priority and map to the four brain
    severity keys (blocker/critical/major/minor).  Unknown labels (e.g.
    'Unassigned') are counted toward the total but not by_severity — they do not
    trigger risk gates, which is intentionally conservative.
    """
    labels: list[str] = defect_priority.get("labels", [])
    matrix: dict[str, list[int]] = defect_priority.get("matrix", {})

    # Sum each priority column across all active statuses.
    col_totals: dict[str, int] = {lbl: 0 for lbl in labels}
    for status_vals in matrix.values():
        for i, count in enumerate(status_vals):
            if i < len(labels) and count is not None:
                col_totals[labels[i]] = col_totals.get(labels[i], 0) + int(count)

    by_severity: dict[str, int] = {"blocker": 0, "critical": 0, "major": 0, "minor": 0}
    total = 0
    for lbl, count in col_totals.items():
        total += count
        mapped = _PRIORITY_MAP.get(lbl)
        if mapped:
            by_severity[mapped] += count
        # Unknown labels (e.g. 'Unassigned') add to total but not to by_severity.

    return {"total": total, "by_severity": by_severity}


def _extract_programme(ir_name: str) -> str:
    """Derive the programme code from the release name string.

    The RKT HTML report carries no dedicated programme field. Programme codes
    appear as prefixes (``AIMS - ``, ``PIMS - ``, ``R5 ``), suffixes
    (``(ME&Q)``, ``(NEO)``), or embedded tokens (``R@W``).

    Returns the matched code, or ``"OSM"`` for releases that carry no code —
    these are native to the current value stream.
    """
    for pattern, code in _PROGRAMME_PATTERNS:
        if pattern.search(ir_name):
            return code
    return "OSM"


def _extract_relationship(ir_name: str) -> dict[str, str] | None:
    """Parse a structured enabler relationship from the release name, if present.

    Some releases exist solely as prerequisites for another release and encode
    this as ``(Dependency for: X; Launch: Y)`` inside their ``ir_name``.
    Returns ``{"dependency_for": X, "enables_release": Y}`` when found, or
    ``None`` for all ordinary releases.

    The ``enables_release`` value may contain nested parentheses (e.g.
    ``"RetirePlus Pro (Adopt & Manage)"``) — the regex matches to the last
    closing paren on the string so inner parens are preserved verbatim.
    """
    m = _DEPENDENCY_RE.search(ir_name)
    if not m:
        return None
    return {
        "dependency_for": m.group(1).strip(),
        "enables_release": m.group(2).strip(),
    }


def _normalize_name(name: str) -> str:
    """HTML-unescape and collapse whitespace for robust TOC name matching.

    TOC link text may contain HTML entities (``&amp;`` → ``&``) and extra
    spaces; ``ir_name`` values from ``__REPORT__`` JSON are already unescaped.
    Normalising both sides before comparison removes entity and spacing
    differences so names like ``"Before &amp; After (Accum)"`` match
    ``"Before & After (Accum)"``.
    """
    return _SPACE_RE.sub(" ", _html.unescape(name)).strip()


def _parse_toc(html: str) -> dict[str, str]:
    """Parse the Table of Contents slide and return ``{normalized_ir_name: vs_name}``.

    The TOC slide (identified by ``data-ribbon="Table of Contents"``) groups every
    release under its business value-stream name (ADR-0021).  This mapping is the
    authoritative source of *which value stream a release serves*, independent of
    the programme code embedded in its ``ir_name``.

    Returns an empty dict when the TOC slide is absent (old-format reports or
    synthetic HTML in tests that omit the TOC).
    """
    m = _TOC_SLIDE_RE.search(html)
    if not m:
        return {}
    toc_html = m.group(1)
    result: dict[str, str] = {}
    current_vs: str | None = None
    for line in toc_html.splitlines():
        line = line.strip()
        vs_m = _TOC_VS_RE.search(line)
        if vs_m:
            # New value-stream section starts; update the active label.
            current_vs = _normalize_name(vs_m.group(1))
            continue
        if current_vs is None:
            continue
        rel_m = _TOC_REL_RE.search(line)
        if rel_m:
            result[_normalize_name(rel_m.group(1))] = current_vs
    return result


def _e2e_latest(e2e_overall: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the latest E2E test counts from the per-release e2e_overall series.

    Returns ``None`` for releases with no E2E data (sparse in the RKT report —
    roughly 4 of 41 releases have it), triggering the E2E-absent fallback in the
    TestReadiness assessor (ADR-0012 §3).
    Null entries are filtered — the series may be padded with nulls for future dates.
    """
    passed_raw: list[Any] = e2e_overall.get("passed", [])
    passed = [v for v in passed_raw if v is not None]
    if not passed:
        return None
    failed = [v for v in e2e_overall.get("failed", []) if v is not None]
    planned = [v for v in e2e_overall.get("planned", []) if v is not None]
    return {
        "passed": int(passed[-1]),
        "failed": int(failed[-1]) if failed else 0,
        "planned": int(planned[-1]) if planned else int(passed[-1]),
    }
