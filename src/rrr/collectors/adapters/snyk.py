"""Snyk adapter — runs ``snyk test --json`` and maps CVE counts to SecurityInput.

This is a subprocess-based adapter that shells out to the Snyk CLI. It targets
the ``security`` dimension and populates the CVE count fields that Snyk reports
natively. SAST status is left as ``"not_run"`` because ``snyk test`` performs
Software Composition Analysis (SCA), not static code analysis.

Snyk CLI prerequisites:

- ``snyk`` must be installed and on ``PATH`` (``npm install -g snyk``).
- ``SNYK_TOKEN`` environment variable must be set to a valid API token.

``snyk test`` exits with code 1 when vulnerabilities are found and code 0 when
none are found. This adapter treats both as a successful scan; only a non-zero
exit code other than 1 (e.g. 2 = authentication error, 3 = unsupported project)
is treated as a collection failure.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from rrr.collectors.base import BaseCollector, CollectorConfig

# Snyk exit codes with defined meanings.
_SNYK_EXIT_VULN_FOUND = 1      # vulnerabilities found — not an error
_SNYK_EXIT_AUTH_ERROR = 2      # authentication failure
_SNYK_EXIT_UNSUPPORTED = 3     # unsupported project type


class SnykAdapterError(Exception):
    """Raised when the Snyk CLI is unavailable, authentication fails, or output is invalid."""


class SnykAdapter(BaseCollector):
    """Runs ``snyk test --json`` and maps CVE counts to SecurityInput (ADR-0023 Phase 2).

    Populates ``open_critical_cves`` and ``open_high_cves`` from the total count of
    open vulnerabilities at each severity level.  ``sast_status`` is always left as
    ``"not_run"`` because Snyk performs SCA, not SAST; a separate SAST tool (e.g.
    SonarQube) should populate that field.

    Fields populated:

    - ``open_critical_cves``: count of CRITICAL severity vulnerabilities.
    - ``open_high_cves``: count of HIGH severity vulnerabilities.
    - ``sast_status``: always ``"not_run"`` (Snyk is SCA, not SAST).

    Fields *not* populated (left to InputContract defaults):

    - ``dast_status``, ``license_approved``, ``data_privacy_approved``,
      ``pen_test_passed`` — require separate tooling or manual sign-off.
    """

    def __init__(
        self,
        project_path: Path | str = ".",
        snyk_args: list[str] | None = None,
    ) -> None:
        """Configure the adapter for the target project directory.

        Args:
            project_path: Directory containing the project's dependency manifest
                (e.g. ``pyproject.toml``, ``package.json``). Defaults to the
                current working directory.
            snyk_args: Optional extra arguments appended to the ``snyk test``
                invocation (e.g. ``["--severity-threshold=high"]``).
        """
        self._project_path = Path(project_path)
        self._extra_args: list[str] = snyk_args or []

    @property
    def dimension(self) -> str:
        """Return the target dimension name for this adapter."""
        return "security"

    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Run ``snyk test --json`` and return a partial SecurityInput dict.

        Counts CRITICAL and HIGH severity vulnerabilities from the Snyk JSON output
        and maps them to the corresponding SecurityInput fields.

        Args:
            config: Runtime context provided by ``CollectorRunner``.  Not used by
                this subprocess adapter but required by the ``BaseCollector`` contract.

        Returns:
            Partial dict ready for ``SecurityInput.model_validate()``.

        Raises:
            SnykAdapterError: If ``snyk`` is not on PATH, authentication fails,
                the project type is unsupported, or the JSON output is malformed.
        """
        self._check_token()
        raw_output = self._run_snyk()
        parsed = self._parse_output(raw_output)

        critical_count = self._count_by_severity(parsed, "critical")
        high_count = self._count_by_severity(parsed, "high")

        return {
            # Snyk is SCA, not SAST — leave sast_status for a dedicated SAST tool.
            "sast_status": "not_run",
            "open_critical_cves": critical_count,
            "open_high_cves": high_count,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_token(self) -> None:
        """Fail fast if the Snyk token is absent before shelling out.

        Raises:
            SnykAdapterError: If ``SNYK_TOKEN`` is not set in the environment.
        """
        if not os.environ.get("SNYK_TOKEN"):
            raise SnykAdapterError(
                "SNYK_TOKEN environment variable is not set. "
                "Set it to a valid Snyk API token before running the adapter."
            )

    def _run_snyk(self) -> str:
        """Execute ``snyk test --json`` and return the raw stdout string.

        Raises:
            SnykAdapterError: If ``snyk`` is not found, authentication fails
                (exit 2), or the project type is unsupported (exit 3).
        """
        cmd = ["snyk", "test", "--json"] + self._extra_args
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._project_path),
            )
        except FileNotFoundError as exc:
            # snyk binary not found on PATH.
            raise SnykAdapterError(
                "snyk CLI not found. Install it with: npm install -g snyk"
            ) from exc

        if proc.returncode == _SNYK_EXIT_AUTH_ERROR:
            raise SnykAdapterError(
                "Snyk authentication failed (exit code 2). "
                "Check that SNYK_TOKEN is correct and has not expired."
            )
        if proc.returncode == _SNYK_EXIT_UNSUPPORTED:
            raise SnykAdapterError(
                f"Snyk does not support this project type (exit code 3). "
                f"Project path: {self._project_path}"
            )
        # Exit 0 = no vulns, 1 = vulns found — both are valid scan outcomes.
        return proc.stdout

    @staticmethod
    def _parse_output(raw: str) -> dict[str, Any]:
        """Parse the JSON emitted by ``snyk test --json``.

        Raises:
            SnykAdapterError: If the output is empty or not valid JSON.
        """
        if not raw.strip():
            raise SnykAdapterError(
                "snyk produced no output. Ensure the project has a supported "
                "dependency manifest (pyproject.toml, package.json, etc.)."
            )
        try:
            result: dict[str, Any] = json.loads(raw)
            return result
        except json.JSONDecodeError as exc:
            raise SnykAdapterError(
                f"Failed to parse snyk JSON output: {exc}"
            ) from exc

    @staticmethod
    def _count_by_severity(parsed: dict[str, Any], severity: str) -> int:
        """Count vulnerabilities at the given severity level.

        Handles both the standard ``snyk test`` output shape (``vulnerabilities``
        list) and the multi-project shape (``vulnerabilities`` key at the root).
        Deduplicates by ``id`` to avoid inflating counts from multiple dependency
        paths to the same vulnerability.
        """
        vulns: list[dict[str, Any]] = parsed.get("vulnerabilities", [])
        seen: set[str] = set()
        count = 0
        for vuln in vulns:
            if vuln.get("severity", "").lower() != severity:
                continue
            vuln_id = vuln.get("id", "")
            if vuln_id and vuln_id in seen:
                # Same CVE reached via a different dependency path — skip.
                continue
            seen.add(vuln_id)
            count += 1
        return count
