"""Environment input contract — ``environment.json`` (FR-3, env-dep-schema.md).

RRR-owned contract (JSON canonical; CSV and localhost-API forms carry the same
payload). Provisioning drives the numeric score; stability drives risk severity,
not the number (a ``validated`` component that is ``down`` still scores 1.00 but
raises a critical risk). The scoring/severity mapping itself lives in the
Environment assessor (M3); these models only validate shape and enum membership.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from rrr.models.base import InputContract
from rrr.models.enums import ProvisioningStatus, StabilityStatus


class ComponentStatus(InputContract):
    """One environment component's readiness."""

    name: str = Field(min_length=1)
    provisioning: ProvisioningStatus
    stability: StabilityStatus
    notes: str = ""


class EnvironmentInput(InputContract):
    """Environment snapshot for a release (FR-3). Empty ``components`` → the
    dimension is unavailable and degrades gracefully (ADR-0005)."""

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: datetime | None = None
    components: list[ComponentStatus] = Field(min_length=1)
