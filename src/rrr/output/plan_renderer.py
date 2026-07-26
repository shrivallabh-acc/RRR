"""Jinja2-based action-plan renderer for ``AssessmentOutputModel`` (M2, FR output quality).

Renders a pre-release work checklist from an assessment: risk factors grouped by
severity (CRITICAL → blockers, MAJOR → required, MINOR → recommended), LLM
remediation steps as ``- [ ]`` checkboxes, and a list of unavailable dimensions
that need re-assessment. Intended for release managers, not engineers reading logs.
"""

from __future__ import annotations

from rrr.models.assessment import AssessmentOutputModel
from rrr.models.enums import RiskSeverity


class PlanRenderer:
    """Renders an ``AssessmentOutputModel`` as an actionable pre-release checklist.

    Uses the bundled ``action_plan.md.j2`` Jinja2 template. The output is a
    Markdown document a release manager can paste into a ticket or team message.
    Instantiation requires Jinja2 (``pip install -e ".[templates]"``).
    """

    def __init__(self) -> None:
        """Load the Jinja2 environment and compile the action-plan template.

        Raises ``ImportError`` with a helpful message if Jinja2 is not installed.
        """
        try:
            from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
        except ImportError as exc:
            raise ImportError(
                'Jinja2 is required for plan output. Install it with: pip install -e ".[templates]"'
            ) from exc

        env = Environment(
            loader=PackageLoader("rrr.output", "templates"),
            autoescape=select_autoescape([]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = env.get_template("action_plan.md.j2")

    def render(self, output: AssessmentOutputModel) -> str:
        """Render ``output`` as a Markdown action-plan checklist.

        Pre-computes the severity buckets so the template stays logic-free.
        Blockers are CRITICAL risks + triggered gates; Required are MAJOR risks;
        Recommended are MINOR risks. Unavailable dimensions are surfaced as
        items needing re-assessment.

        :param output: the assessment result to turn into a work plan.
        :returns: a Markdown checklist string.
        """
        blockers = [r for r in output.risk_factors if r.severity == RiskSeverity.CRITICAL]
        required = [r for r in output.risk_factors if r.severity == RiskSeverity.MAJOR]
        recommended = [r for r in output.risk_factors if r.severity == RiskSeverity.MINOR]
        unavailable = [d for d in output.dimensions if not d.available]
        return self._template.render(
            o=output,
            blockers=blockers,
            required=required,
            recommended=recommended,
            unavailable=unavailable,
        )
