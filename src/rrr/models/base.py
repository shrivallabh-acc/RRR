"""Shared Pydantic base classes and timestamp helpers (ADR-0004, NFR-3, NFR-5).

Two validation postures are used across the model layer:

* ``RRRModel`` — for RRR's own internal/output value objects. It is **frozen**
  (immutable value objects, DDD style) and **forbids unknown fields** so typos
  and accidental mutation fail loudly.
* ``InputContract`` — for data ingested from outside RRR (the upstream brain
  extract, environment/dependency sources). It **ignores unknown fields** so
  upstream additions do not break ingestion (forward-compatible anti-corruption
  boundary); we validate only what we consume.

``utc_now`` / ``iso_millis`` centralise the ISO-8601 millisecond-precision
timestamp rule (NFR-3) so every model serialises timestamps identically.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


def utc_now() -> datetime:
    """Timezone-aware current time in UTC (default factory for timestamps)."""
    return datetime.now(UTC)


def iso_millis(value: datetime) -> str:
    """Serialise a ``datetime`` to ISO 8601 with exactly millisecond precision (NFR-3).

    Example: ``2026-06-14T10:00:00.000Z``. Naive datetimes are assumed UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RRRModel(BaseModel):
    """Base for RRR-owned value objects: immutable and strict.

    Frozen (hashable, no accidental mutation) and ``extra="forbid"`` (unknown
    fields are an error). Timestamps serialise at millisecond precision.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        ser_json_timedelta="iso8601",
    )


class InputContract(BaseModel):
    """Base for data ingested from outside RRR (brain / environment / dependency).

    Tolerates unknown upstream fields (``extra="ignore"``) so the contract is
    forward-compatible; we validate only the fields RRR actually consumes.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )
