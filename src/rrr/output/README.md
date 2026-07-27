# Output

Jinja2-based output renderers that turn an `AssessmentOutputModel` into formatted
reports. Requires `pip install "rrr[templates]"` for Markdown, Plan, and HTML formats.

---

## Renderers

| Class | Format flag | Output |
|---|---|---|
| `MarkdownRenderer` | `--format markdown` | Full Markdown report with dimension breakdown, risk table, and rationale |
| `PlanRenderer` | `--format plan` | Action-plan checklist — CRITICAL/MAJOR/MINOR-bucketed `- [ ]` items for remediation |
| `HtmlRenderer` | `--format html` | Self-contained Bootstrap 5 HTML page (CDN links) |

The `text` and `json` formats are handled directly in `cli.py` without Jinja2.

---

## Templates

```
src/rrr/output/
  templates/
    report.md.j2         ← MarkdownRenderer
    plan.md.j2           ← PlanRenderer
    report.html.j2       ← HtmlRenderer
  markdown_renderer.py
  plan_renderer.py
  html_renderer.py
  __init__.py
```

---

## Usage in code

```python
from rrr.output import MarkdownRenderer, PlanRenderer, HtmlRenderer

renderer = MarkdownRenderer()
md = renderer.render(assessment_output_model)

plan = PlanRenderer().render(assessment_output_model)

html = HtmlRenderer().render(assessment_output_model)
```

---

## CLI usage

```powershell
# Markdown report (requires rrr[templates])
rrr --release "RetirePlus RC" --format markdown > report.md

# Remediation action-plan checklist
rrr --release "RetirePlus RC" --format plan > plan.md

# Self-contained HTML report
rrr --release "RetirePlus RC" --format html > report.html
```

---

## Customising templates

Templates use Jinja2. The variable available in all templates is `result` — a
serialised dict of `AssessmentOutputModel`. Common fields:

```jinja2
{{ result.release }}
{{ result.verdict }}
{{ result.score }}
{{ result.aggregate_confidence | round(2) }}

{% for dim in result.dimensions %}
  {{ dim.dimension }} — {{ dim.score | round(2) }} ({{ dim.status }})
  {% for rf in dim.risk_factors %}
    [{{ rf.severity }}] {{ rf.description }}
  {% endfor %}
{% endfor %}
```
