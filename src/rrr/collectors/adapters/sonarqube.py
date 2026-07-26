"""SonarQube adapter — queries the SonarQube REST API and maps issue counts to SecurityInput.

This is an HTTP adapter that calls the SonarQube ``/api/issues/search`` endpoint to
count open VULNERABILITY-type issues at CRITICAL and MAJOR severity.  It derives
``sast_status`` from whether any such issues exist and populates the CVE count fields
for security-tool findings.

Prerequisites:

- ``base_url``: the SonarQube server URL, e.g. ``http://sonarqube.internal``.
- ``project_key``: the SonarQube project key, e.g. ``com.example:retail-banking``.
- ``SONARQUBE_TOKEN``: environment variable containing a valid API token.

ADR-0010 (local-first): this adapter makes an outbound HTTP call and therefore must
only be used in Phase 2 (external, opt-in) contexts.  The caller is responsible for
ensuring the ``base_url`` host is on the approved allow-list before constructing the
adapter.  A future revision will inject the ``ConfigLoader`` allow-list directly.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from rrr.collectors.base import BaseCollector, CollectorConfig

# SonarQube severity labels that map to a VULNERABILITY finding.
_CRITICAL_SEVERITIES = frozenset({"CRITICAL", "BLOCKER"})
_HIGH_SEVERITIES = frozenset({"MAJOR"})

# Page size for the issues API — fetch up to this many issues per request.
_PAGE_SIZE = 500


class SonarQubeAdapterError(Exception):
    """Raised when the SonarQube API is unreachable, returns an error, or token is missing."""


class SonarQubeAdapter(BaseCollector):
    """Queries SonarQube REST API and maps VULNERABILITY issue counts to SecurityInput.

    ADR-0023 Phase 2 adapter.

    Calls ``GET /api/issues/search?componentKeys=<project>&types=VULNERABILITY``
    and counts open issues by severity to populate SecurityInput fields.

    Fields populated:

    - ``sast_status``: ``"passed"`` when no open VULNERABILITY issues exist;
      ``"failed"`` when CRITICAL or MAJOR issues are found.
    - ``open_critical_cves``: count of BLOCKER + CRITICAL severity vulnerabilities.
    - ``open_high_cves``: count of MAJOR severity vulnerabilities.

    Fields *not* populated (left to InputContract defaults):

    - ``dast_status``, ``license_approved``, ``data_privacy_approved``,
      ``pen_test_passed`` — require separate tooling or manual sign-off.
    """

    def __init__(
        self,
        base_url: str,
        project_key: str,
        timeout_s: int = 30,
    ) -> None:
        """Configure the adapter with the SonarQube server and project coordinates.

        The caller must ensure ``base_url`` points to an allowed host (ADR-0010).
        Credentials are read from ``SONARQUBE_TOKEN`` at collect-time.

        Args:
            base_url: SonarQube server root URL, e.g. ``http://sonarqube.internal``.
                Must not end with a slash.
            project_key: SonarQube project key, e.g. ``com.example:retail-banking``.
            timeout_s: HTTP request timeout in seconds.  Default 30.
        """
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._timeout_s = timeout_s

    @property
    def dimension(self) -> str:
        """Return the target dimension name for this adapter."""
        return "security"

    def collect(self, config: CollectorConfig) -> dict[str, Any]:
        """Query SonarQube for open VULNERABILITY issues and return a partial SecurityInput dict.

        Args:
            config: Runtime context provided by ``CollectorRunner``.  Not used by
                this HTTP adapter but required by the ``BaseCollector`` contract.

        Returns:
            Partial dict ready for ``SecurityInput.model_validate()``.

        Raises:
            SonarQubeAdapterError: If ``SONARQUBE_TOKEN`` is absent, the API is
                unreachable, returns a non-200 status, or the response is not valid JSON.
        """
        token = self._check_token()
        issues = self._fetch_all_issues(token)

        critical_count = sum(
            1 for i in issues if i.get("severity", "") in _CRITICAL_SEVERITIES
        )
        high_count = sum(
            1 for i in issues if i.get("severity", "") in _HIGH_SEVERITIES
        )

        sast_status = "failed" if (critical_count + high_count) > 0 else "passed"

        return {
            "sast_status": sast_status,
            "open_critical_cves": critical_count,
            "open_high_cves": high_count,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_token(self) -> str:
        """Read and return the SonarQube API token from the environment.

        Raises:
            SonarQubeAdapterError: If ``SONARQUBE_TOKEN`` is not set.
        """
        token = os.environ.get("SONARQUBE_TOKEN", "")
        if not token:
            raise SonarQubeAdapterError(
                "SONARQUBE_TOKEN environment variable is not set. "
                "Set it to a valid SonarQube user or project token."
            )
        return token

    def _fetch_all_issues(self, token: str) -> list[dict[str, Any]]:
        """Paginate through the SonarQube issues API and return all open VULNERABILITY issues.

        SonarQube paginates results; this method fetches all pages until the
        total is exhausted or no ``issues`` are returned.

        Args:
            token: SonarQube API token for HTTP Basic Auth.

        Returns:
            Flat list of issue dicts from all pages.

        Raises:
            SonarQubeAdapterError: On HTTP error, connection failure, or invalid JSON.
        """
        all_issues: list[dict[str, Any]] = []
        page = 1
        while True:
            page_issues, total = self._fetch_page(token, page)
            all_issues.extend(page_issues)
            if len(all_issues) >= total or not page_issues:
                break
            page += 1
        return all_issues

    def _fetch_page(
        self,
        token: str,
        page: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch one page of VULNERABILITY issues from SonarQube.

        Args:
            token: SonarQube API token for HTTP Basic Auth.
            page: 1-based page number.

        Returns:
            Tuple of (issues list, total issue count from the response).

        Raises:
            SonarQubeAdapterError: On connection failure, non-200 status, or JSON error.
        """
        params = urllib.parse.urlencode({
            "componentKeys": self._project_key,
            "types": "VULNERABILITY",
            "statuses": "OPEN,CONFIRMED,REOPENED",
            "ps": _PAGE_SIZE,
            "p": page,
        })
        url = f"{self._base_url}/api/issues/search?{params}"

        # SonarQube uses HTTP Basic Auth with the token as the username and empty password.
        auth = urllib.parse.quote(token, safe="") + ":"
        import base64
        auth_header = "Basic " + base64.b64encode(auth.encode()).decode()

        req = urllib.request.Request(url, headers={"Authorization": auth_header})

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Non-2xx response — surface the status for diagnosis.
            raise SonarQubeAdapterError(
                f"SonarQube API returned HTTP {exc.code} for project "
                f"{self._project_key!r} at {self._base_url}. "
                "Check that the project key is correct and the token has read access."
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            # Connection refused, DNS failure, timeout, etc.
            raise SonarQubeAdapterError(
                f"Could not connect to SonarQube at {self._base_url}: {exc}. "
                "Ensure the host is reachable and the URL is correct."
            ) from exc

        try:
            data: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SonarQubeAdapterError(
                f"SonarQube returned non-JSON response: {exc}"
            ) from exc

        issues: list[dict[str, Any]] = data.get("issues", [])
        total: int = data.get("total", len(issues))
        return issues, total
