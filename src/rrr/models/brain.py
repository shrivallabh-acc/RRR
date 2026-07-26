"""Brain input contract — ``<value-stream>-history.json`` (ADR-0012, brain-schema.md).

The normalized, pre-aggregated extract of the upstream RKT Program Metrics report
that RRR consumes via the ``RKTBrainReader`` tool. Assessors only ever see this
contract, never the raw HTML report (anti-corruption boundary).

These are :class:`InputContract` models: unknown upstream fields are ignored so
the contract is forward-compatible. The models carry *shape only* — completion
ratios, variance, and the test composite are derived in the assessors (M3), not
here, so all deterministic scoring stays auditable in one place.

``programme`` and ``release_relationship`` are extracted from the ``ir_name`` string
by ``rrr-ingest`` (ADR-0018). ``toc_value_stream`` is the business value-stream name
from the TOC slide of the HTML report (ADR-0021); it is ``None`` for brain files
ingested before ADR-0021. The RKT HTML report carries no separate programme field —
all grouping information is encoded in the release name.  Old brain files that
pre-date these additions load fine because ``ReleaseRecord`` is an
:class:`InputContract` and missing fields fall back to their defaults.
"""

from __future__ import annotations

from pydantic import Field, NonNegativeInt

from rrr.models.base import InputContract


class Summary(InputContract):
    """Per-release story-point summary → Scope (FR-1)."""

    total: NonNegativeInt
    closed: NonNegativeInt
    remaining: NonNegativeInt
    pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Upstream-reported percent; RRR recomputes from closed/total.",
    )


class WeeklyPoint(InputContract):
    """One point of recent velocity (``weekly_last3``) → Scope narrative context."""

    week: str
    value: NonNegativeInt


class DefectSeverity(InputContract):
    """Open-defect counts broken down by severity → Test defect-trend risk (FR-4)."""

    blocker: NonNegativeInt = 0
    critical: NonNegativeInt = 0
    major: NonNegativeInt = 0
    minor: NonNegativeInt = 0


class DefectsOpen(InputContract):
    """Open defects for the release."""

    total: NonNegativeInt
    by_severity: DefectSeverity


class PVPoint(InputContract):
    """Latest earned-value point (``pv_latest``) → Estimation (FR-2)."""

    planned: float = Field(
        ge=0.0,
        description="Planned value (0 means no PV data yet; estimation marks unavailable).",
    )
    actual: float = Field(ge=0.0)


class E2EPoint(InputContract):
    """Latest end-to-end test result (``e2e_latest``) → Test E2E sub-score (FR-4).

    Optional on the parent release: when absent, the assessor drops the E2E
    sub-component and renormalizes with reduced confidence (ADR-0012)."""

    passed: NonNegativeInt
    failed: NonNegativeInt
    planned: NonNegativeInt = Field(
        description="Planned E2E count; (passed+failed)<planned means unrun tests.",
    )


class ReleaseRelationship(InputContract):
    """Enabler/dependency relationship parsed from the ``ir_name`` string (ADR-0018).

    Some releases exist solely to enable another release in a different programme.
    The RKT report encodes this as ``(Dependency for: X; Launch: Y)`` inside the
    release name. This model surfaces that relationship in a structured form so it
    can appear in reports and inform future dependency-chain scoring.
    """

    dependency_for: str = Field(
        description="Programme or release this enabler release unblocks (e.g. 'DIST').",
    )
    enables_release: str = Field(
        description="Downstream release name that depends on this one completing first.",
    )


class ReleaseRecord(InputContract):
    """One release (``ir_name``) within a snapshot — the subject of one assessment."""

    ir_name: str = Field(min_length=1)
    programme: str = Field(
        default="OSM",
        description=(
            "Programme code extracted from ir_name during ingest "
            "(e.g. AIMS, PIMS, EIMS, R5, ME&Q). 'OSM' means no programme prefix was found "
            "— these are native releases for the current value stream."
        ),
    )
    release_relationship: ReleaseRelationship | None = Field(
        default=None,
        description=(
            "Populated only for enabler/dependency releases whose ir_name contains "
            "'(Dependency for: X; Launch: Y)'. Null for all normal releases."
        ),
    )
    summary: Summary
    weekly_last3: list[WeeklyPoint] = Field(default_factory=list)
    defects_open: DefectsOpen
    defects_closed_cumulative: NonNegativeInt = 0
    defect_trend_last5: list[NonNegativeInt] = Field(default_factory=list)
    sq_avg: float = Field(ge=0.0, le=3.0, description="Static-quality average on a 0-3 scale.")
    sq_below_1: list[str] = Field(
        default_factory=list,
        description="Repos with quality below 1.0 (risk flags).",
    )
    toc_value_stream: str | None = Field(
        default=None,
        description=(
            "Business value-stream name from the TOC slide of the RKT HTML report "
            "(ADR-0021). Examples: 'Account Management', 'Education & Advice', "
            "'Tech Foundation'.  Null for releases ingested before ADR-0021."
        ),
    )
    pv_latest: PVPoint
    e2e_latest: E2EPoint | None = None


class BrainSnapshot(InputContract):
    """One weekly cycle. Holds every release tracked that week."""

    date: str = Field(min_length=1, description="Snapshot date (ISO date, e.g. 2026-05-28).")
    releases: list[ReleaseRecord] = Field(min_length=1)


class BrainHistory(InputContract):
    """Top-level file: the full timestamped history for one value stream.

    Snapshot/release *selection* (latest by default, scope-creep baseline across
    snapshots) is the ``RKTBrainReader`` tool's responsibility, not the model's.
    """

    value_stream: str = Field(min_length=1)
    snapshots: list[BrainSnapshot] = Field(min_length=1)
