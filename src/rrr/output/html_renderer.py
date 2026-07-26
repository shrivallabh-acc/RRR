"""Jinja2-based HTML renderer for ``AssessmentOutputModel`` (M5, FR output quality).

Renders a self-contained HTML report: verdict badge, score bar, per-dimension
table, risk factor list, remediation checklist, and audit footer. Requires no
extra runtime dep beyond Jinja2 (already used by ``MarkdownRenderer``).

The rendered file is fully self-contained — Bootstrap 5 is loaded from CDN so
the report can be opened in any browser without a server.
"""

from __future__ import annotations

from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import RiskSeverity

# Bootstrap badge classes per verdict label (lower-cased for safe lookup).
_VERDICT_BADGE: dict[str, str] = {
    "go": "success",
    "no_go": "danger",
    "conditional": "warning",
    "incomplete": "secondary",
}


class HtmlRenderer:
    """Renders an ``AssessmentOutputModel`` to a self-contained HTML string.

    Uses the bundled ``verdict_report.html.j2`` Jinja2 template with Bootstrap 5
    loaded from CDN. The output file can be opened directly in a browser.
    Instantiation requires Jinja2 (``pip install -e ".[templates]"``).
    """

    def __init__(self) -> None:
        """Load the Jinja2 environment and compile the HTML template.

        Raises ``ImportError`` with a helpful message if Jinja2 is not installed.
        """
        try:
            from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
        except ImportError as exc:
            raise ImportError(
                'Jinja2 is required for HTML output. Install it with: pip install -e ".[templates]"'
            ) from exc

        env = Environment(
            loader=PackageLoader("rrr.output", "templates"),
            # Enable HTML autoescaping so any narrative text containing < or & is safe.
            autoescape=select_autoescape(["html", "j2"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = env.get_template("verdict_report.html.j2")

    def render(self, output: AssessmentOutputModel) -> str:
        """Render ``output`` as a self-contained HTML report string.

        Pre-computes derived values (badge class, severity buckets, score percent)
        so the template stays logic-free.

        :param output: the assessment result to render.
        :returns: a complete HTML document as a string.
        """
        verdict_key = output.verdict.value.lower()
        badge_class = _VERDICT_BADGE.get(verdict_key, "secondary")
        blockers = [r for r in output.risk_factors if r.severity == RiskSeverity.CRITICAL]
        required = [r for r in output.risk_factors if r.severity == RiskSeverity.MAJOR]
        recommended = [r for r in output.risk_factors if r.severity == RiskSeverity.MINOR]
        return self._template.render(
            o=output,
            badge_class=badge_class,
            blockers=blockers,
            required=required,
            recommended=recommended,
        )
