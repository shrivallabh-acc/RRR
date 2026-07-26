"""Jinja2-based Markdown renderer for ``AssessmentOutputModel`` (M2, FR output quality).

Loads ``templates/verdict_report.md.j2`` via ``PackageLoader`` so it works both
in editable installs and in built wheels. The rendered Markdown is a self-contained
readiness report: verdict summary, per-dimension table, risk factors, remediation
steps, and a compact audit footer.
"""

from __future__ import annotations

from rrr.models.assessment import AssessmentOutputModel

# Jinja2 is the optional [templates] dep group.  Import is deferred to __init__
# of MarkdownRenderer so missing the dep produces a clear ImportError at
# instantiation time rather than at module import time.


class MarkdownRenderer:
    """Renders an ``AssessmentOutputModel`` to a Markdown string.

    Uses the bundled ``verdict_report.md.j2`` Jinja2 template. Instantiation
    requires Jinja2 (``pip install -e ".[templates]"``); rendering is then
    a single ``render()`` call.
    """

    def __init__(self) -> None:
        """Load the Jinja2 environment and compile the template.

        Raises ``ImportError`` with a helpful message if Jinja2 is not installed.
        """
        try:
            from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
        except ImportError as exc:
            raise ImportError(
                "Jinja2 is required for Markdown output. "
                'Install it with: pip install -e ".[templates]"'
            ) from exc

        env = Environment(
            loader=PackageLoader("rrr.output", "templates"),
            autoescape=select_autoescape([]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = env.get_template("verdict_report.md.j2")

    def render(self, output: AssessmentOutputModel) -> str:
        """Render ``output`` as a Markdown report string.

        :param output: the assessment result to render.
        :returns: a complete Markdown document as a string.
        """
        return self._template.render(o=output)
