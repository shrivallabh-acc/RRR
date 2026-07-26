"""Failure mode input contract — ``failure_mode.json`` (ADR-0016 item 12).

RRR-owned contract describing resilience engineering posture: failure modes,
circuit breakers, chaos testing, and graceful degradation evidence.
Gate-only dimension (weight = 0): contributes only via risk-factor severity.

Scoring lives in FailureModeAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class FailureModeInput(InputContract):
    """Resilience and failure-mode posture for a release (ADR-0016 item 12, gate-only).

    Fields default to the most conservative values (undocumented, absent, not run)
    so a missing file assesses pessimistically and the gate triggers, prompting
    the team to provide evidence before shipping.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the resilience posture was assessed.",
    )
    failure_modes_documented: bool = Field(
        default=False,
        description=(
            "True if failure modes for all critical paths have been catalogued "
            "(e.g. in an FMEA register or equivalent)."
        ),
    )
    critical_paths_covered_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of critical user journeys that have documented failure mode "
            "analysis and mitigation strategies."
        ),
    )
    circuit_breakers_configured: bool = Field(
        default=False,
        description=(
            "True if circuit breakers (or equivalent back-pressure mechanisms) are "
            "configured on all external service calls in the critical path."
        ),
    )
    timeout_policies_defined: bool = Field(
        default=False,
        description=(
            "True if explicit timeout and retry policies are defined and tested "
            "for every external dependency call."
        ),
    )
    chaos_tests_run: bool = Field(
        default=False,
        description="True if chaos / fault-injection tests were run for this release.",
    )
    chaos_pass_rate_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of chaos experiments that the system survived within "
            "acceptable degradation bounds. 0 if tests were not run."
        ),
    )
    chaos_test_date: str | None = Field(
        default=None,
        description="ISO 8601 date of the most recent chaos test run.",
    )
    graceful_degradation_tested: bool = Field(
        default=False,
        description=(
            "True if the system's graceful degradation behaviour (partial failures "
            "returning reduced-capability responses rather than hard errors) has been "
            "validated under simulated dependency failures."
        ),
    )
    fmea_complete: bool = Field(
        default=False,
        description=(
            "True if a Failure Mode and Effects Analysis (FMEA) has been completed "
            "and reviewed for this release."
        ),
    )
    chaos_pass_threshold_pct: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description=(
            "Minimum chaos pass rate percentage that avoids a MAJOR risk factor. "
            "Default 80 % — failing more than one-fifth of experiments is high-risk."
        ),
    )
