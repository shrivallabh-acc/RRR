"""NiceGUI web dashboard package for RRR (ADR-0020, optional `rrr[ui]` dep).

The public surface is :func:`run_ui` in :mod:`rrr.ui.app`.  Nothing in this
package is imported by the core pipeline — the dependency is intentionally
one-way: UI → pipeline, never the other direction.

Install with: ``pip install rrr[ui]``
"""

from rrr.ui.app import run_ui

__all__ = ["run_ui"]
