"""Shared pytest configuration — Hypothesis profiles and test-tier markers.

Hypothesis run profiles
-----------------------
Set the ``HYPOTHESIS_PROFILE`` environment variable to select a profile:

- ``ci``   (default) — 25 examples, fast feedback on every commit / save
- ``full`` — 200 examples, thorough check used at milestone quality gates

PowerShell usage::

    # During development (default — no env-var needed):
    pytest -m "unit or golden" -x -q

    # Full gate (milestone sign-off):
    $env:HYPOTHESIS_PROFILE = "full"; pytest

Test markers
------------
``unit``     — fast unit tests; run on every commit
``golden``   — golden-fixture end-to-end tests; run before every commit
``property`` — Hypothesis property tests; run at the quality gate only
``eval``     — LLM evaluation harness; run at milestone breaks only
``slow``     — any test that consistently takes > 1 second
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# Fast CI profile — 25 examples keeps the property suite under 2 seconds.
settings.register_profile(
    "ci",
    max_examples=25,
    suppress_health_check=[HealthCheck.too_slow],
)

# Full gate profile — 200 examples for thorough invariant exploration.
settings.register_profile(
    "full",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
