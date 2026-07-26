"""Dependency input contract — ``dependency.json`` (FR-5, env-dep-schema.md).

RRR-owned contract (JSON canonical; CSV and localhost-API forms carry the same
payload). Score = (complete AND passed)/total; per-dependency classification
(blocking / at_risk / on_track) is computed in the Dependency assessor (M3).
These models only validate shape and enum membership.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import DependencyCompletion, IntegrationStatus


class DependencyItem(InputContract):
    """One upstream/downstream dependency for the release."""

    name: str = Field(min_length=1)
    completion: DependencyCompletion
    integration: IntegrationStatus
    owner: str = ""
    notes: str = ""


class DependencyInput(InputContract):
    """Dependency snapshot for a release (FR-5). Empty ``dependencies`` → the
    dimension is unavailable and degrades gracefully (ADR-0005)."""

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: datetime | None = None
    dependencies: list[DependencyItem] = Field(min_length=1)
