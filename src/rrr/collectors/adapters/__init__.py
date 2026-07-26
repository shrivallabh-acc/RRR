"""Tool adapters for automated dimension data collection (ADR-0023 Phase 2).

Adapters extend ``BaseCollector`` with ``collect()`` implementations that pull
data from external CI/CD tools rather than prompting interactively. Each adapter
targets one dimension and returns a partial dict that ``CollectorRunner.run()``
validates against the dimension's ``InputContract`` before writing to disk.

Available adapters:

- ``K6Adapter`` — reads a k6 ``--summary-export`` JSON file → ``PerformanceInput``
- ``SnykAdapter`` — runs ``snyk test --json`` subprocess → ``SecurityInput``
- ``SonarQubeAdapter`` — queries SonarQube REST API → ``SecurityInput``

Conventions enforced by all adapters (ADR-0010, ADR-0023):

1. Return a *partial* dict — missing fields fall back to ``InputContract`` defaults.
2. Network adapters validate the target host before connecting; they never call
   arbitrary public endpoints without an explicit allow-list check.
3. Credentials come from environment variables only — never from source or config.
4. Tests mock all external I/O and must pass with no network or tool present.
"""

from rrr.collectors.adapters.k6 import K6Adapter
from rrr.collectors.adapters.snyk import SnykAdapter
from rrr.collectors.adapters.sonarqube import SonarQubeAdapter

__all__ = [
    "K6Adapter",
    "SnykAdapter",
    "SonarQubeAdapter",
]
