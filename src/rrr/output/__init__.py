"""Rendered output layer for RRR assessments (M2/M5, FR output quality).

Provides three renderers for ``AssessmentOutputModel``, all backed by Jinja2:

* ``MarkdownRenderer`` (``--format markdown``) — narrative report: verdict
  summary, dimension table, risk factors, remediation, audit footer.
* ``PlanRenderer`` (``--format plan``) — actionable pre-release checklist:
  risks bucketed by severity, remediation as ``- [ ]`` checkboxes, unavailable
  dimensions surfaced as re-assessment tasks.
* ``HtmlRenderer`` (``--format html``) — self-contained HTML report with
  Bootstrap 5 (CDN), colour-coded verdict badge, score bar, and risk table.

All string-building lives here; the CLI and pipeline stay format-free. Requires
the ``templates`` optional dep group (Jinja2 ≥ 3.1).
"""

from rrr.output.html_renderer import HtmlRenderer
from rrr.output.plan_renderer import PlanRenderer
from rrr.output.renderer import MarkdownRenderer

__all__ = ["HtmlRenderer", "MarkdownRenderer", "PlanRenderer"]
