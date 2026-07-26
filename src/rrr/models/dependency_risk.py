"""Dependency risk input contract — ``dependency_risk.json`` (ADR-0016 item 13).

RRR-owned contract describing supply-chain and third-party dependency risk.
Distinct from DependencyAssessor (which tracks internal programme delivery
completion) — this gate covers software supply-chain integrity and CVE exposure
in transitive dependencies. Gate-only (weight = 0).

Scoring lives in DependencyRiskAssessor; this model only validates shape.
"""

from __future__ import annotations

from pydantic import Field

from rrr.models.base import InputContract


class DependencyRiskInput(InputContract):
    """Software supply-chain risk posture for a release (ADR-0016 item 13, gate-only).

    Fields default to zero/None/False so missing data is conservative rather than
    optimistic — a missing SCA scan defaults to no violations found, but the
    assessor additionally checks whether the scan itself was run.
    """

    schema_version: str = "1.0.0"
    release: str | None = Field(
        default=None,
        description="Brain ir_name this snapshot correlates to.",
    )
    captured_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the dependency risk scan was captured.",
    )
    sca_tool: str | None = Field(
        default=None,
        description="Name of the Software Composition Analysis tool used (e.g. Snyk, Dependabot).",
    )
    sca_scan_date: str | None = Field(
        default=None,
        description="ISO 8601 date of the most recent SCA scan. None means no scan has been run.",
    )
    eol_dependencies_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of direct dependencies that have reached end-of-life and "
            "no longer receive security patches."
        ),
    )
    critical_transitive_cves: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of open critical-severity CVEs in transitive (indirect) dependencies. "
            "These are harder to remediate but pose the same exposure as direct CVEs."
        ),
    )
    high_transitive_cves: int = Field(
        default=0,
        ge=0,
        description="Count of open high-severity CVEs in transitive dependencies.",
    )
    supply_chain_violations: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of supply-chain policy violations detected by the SCA tool "
            "(e.g. unapproved package sources, licence conflicts, unsigned packages)."
        ),
    )
    pinned_dependencies_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of direct dependencies pinned to an exact version. "
            "Floating versions introduce uncontrolled supply-chain risk."
        ),
    )
    known_malicious_packages: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of packages flagged as malicious or typosquatted by the SCA tool "
            "or a threat-intelligence feed. Any non-zero count is an immediate CRITICAL."
        ),
    )
    high_transitive_cve_threshold: int = Field(
        default=10,
        ge=0,
        description=(
            "Maximum acceptable count of high-severity transitive CVEs before a "
            "MAJOR risk factor is raised. Default 10."
        ),
    )
