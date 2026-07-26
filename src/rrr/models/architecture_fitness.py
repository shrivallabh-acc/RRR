"""Architecture fitness input contract — ``architecture_fitness.json`` (ADR-0016 item 15).

RRR-owned contract describing automated architecture test results (fitness functions).
Gate-only dimension (weight = 0): contributes only via risk-factor severity,
ensuring architectural constraints are enforced as hard gates rather than
contributing to a score that can be averaged away.

Scoring lives in ArchitectureFitnessAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class ArchitectureFitnessInput(InputContract):
    """Architecture fitness function results for a release (ADR-0016 item 15, gate-only).

    ``violations`` is a free-form list of violation descriptions for LLM narration;
    the counts (coupling_violations, layering_violations, banned_dependency_violations)
    are the structured signal the assessor gates on.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the fitness function scan was run.",
    )
    tool: str | None = Field(
        default=None,
        description=(
            "Name of the architecture test tool (e.g. ArchUnit, NetArchTest, "
            "Dependency Cruiser, custom script)."
        ),
    )
    scan_date: str | None = Field(
        default=None,
        description="ISO 8601 date the fitness function suite was last executed.",
    )
    fitness_functions_defined: int = Field(
        default=0,
        ge=0,
        description="Total number of architecture fitness functions / tests defined.",
    )
    tests_run: int = Field(
        default=0,
        ge=0,
        description="Number of fitness function tests executed in the latest scan.",
    )
    tests_passed: int = Field(
        default=0,
        ge=0,
        description="Number of tests that passed.",
    )
    tests_failed: int = Field(
        default=0,
        ge=0,
        description="Number of tests that failed.",
    )
    coupling_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of coupling violations: dependencies between components or layers "
            "that violate the team's coupling rules (e.g. domain → infrastructure, "
            "bounded context crossing without an anti-corruption layer)."
        ),
    )
    layering_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of layering violations: calls that skip an architectural layer "
            "(e.g. UI → repository bypassing the service layer)."
        ),
    )
    banned_dependency_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of references to banned packages, modules, or frameworks "
            "that have been explicitly prohibited by architecture decision."
        ),
    )
    violations: list[str] = Field(
        default_factory=list,
        description=(
            "Human-readable descriptions of individual violations for LLM narration. "
            "Each entry is a single sentence describing one rule breach."
        ),
    )
