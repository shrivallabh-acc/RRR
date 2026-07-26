"""Click CLI entry point (FR-16, FR-17).

``rrr --release "<ir_name>"`` prints ``VERDICT: GO  SCORE: 84`` and exits with
a verdict-derived code: 0=GO, 1=NO_GO, 2=CONDITIONAL, 3=ERROR/INCOMPLETE.
Use ``--format json`` (or the legacy ``--verbose``) for the full JSON output,
``--format markdown`` for a human-readable Jinja2-rendered report,
``--format plan`` for an action-plan checklist,
``--format html`` for a self-contained HTML report (Bootstrap 5, CDN),
or ``--dry-run`` to run the full assessment pipeline without writing to SQLite.

``--release`` supports fuzzy matching: if the exact name is not found, a
case-insensitive substring search is tried. Use ``--list-releases`` to print
all available release names for a value stream and exit. Add ``--programme OSM``
(or AIMS, PIMS, etc.) to filter the list or to narrow fuzzy matching to one programme.
"""

from __future__ import annotations

import logging
import sys

import click

from rrr.config import ConfigLoader
from rrr.errors import RRRError
from rrr.models.enums import ReleaseRiskTier, Verdict
from rrr.pipeline import assess, run_and_record

# FR-17 exit codes; INCOMPLETE and any error map to 3.
_EXIT_CODES = {Verdict.GO: 0, Verdict.NO_GO: 1, Verdict.CONDITIONAL: 2}
_ERROR_EXIT = 3


@click.command()
@click.option(
    "--release",
    default=None,
    help="Release ir_name to assess. Supports partial/fuzzy matching.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Optional config YAML; merged over bundled defaults.",
)
@click.option("--value-stream", default=None, help="Override the configured value stream.")
@click.option(
    "--programme",
    default=None,
    help=(
        "Filter to a specific programme (e.g. OSM, AIMS, PIMS). "
        "Scopes --list-releases output and narrows fuzzy --release matching."
    ),
)
@click.option(
    "--tier",
    type=click.Choice(["hotfix", "standard", "major"], case_sensitive=False),
    default=None,
    help=(
        "Release risk tier — selects threshold set from config.tiers (ADR-0016). "
        "hotfix: relaxed thresholds. standard: default. major: strict. "
        "Requires a tiers: block in the config file."
    ),
)
@click.option("--verbose", is_flag=True, help="Emit full JSON (shorthand for --format json).")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown", "plan", "html"], case_sensitive=False),
    default="text",
    help="Output format: text (default), json, markdown, plan (action checklist), or html.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Run the full assessment without persisting to SQLite.",
)
@click.option(
    "--list-releases",
    "list_releases",
    is_flag=True,
    default=False,
    help="Print all release names in the brain file for the given value stream and exit.",
)
def main(
    release: str | None,
    config_path: str | None,
    value_stream: str | None,
    programme: str | None,
    tier: str | None,
    verbose: bool,
    output_format: str,
    dry_run: bool,
    list_releases: bool,
) -> None:
    """Produce a release-readiness verdict for RELEASE."""
    # Reconfigure stdout to UTF-8 so Unicode output (e.g. ✅, →) survives
    # redirection to a file on Windows, where the default encoding is cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s  %(name)s — %(message)s",
        stream=sys.stderr,
    )

    if list_releases:
        _cmd_list_releases(config_path, value_stream, programme)
        return

    if release is None:
        raise click.UsageError("--release is required (use --list-releases to see available names)")

    release_tier = ReleaseRiskTier(tier) if tier is not None else None
    try:
        config = ConfigLoader.load(config_path)
        if dry_run:
            result = assess(config, release=release, value_stream=value_stream, tier=release_tier)
        else:
            result = run_and_record(
                config, release=release, value_stream=value_stream, tier=release_tier
            )
    except RRRError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(_ERROR_EXIT)

    if dry_run:
        # Route to stderr for structured formats so piped output stays machine-parseable.
        click.echo("[DRY RUN — result not persisted]", err=output_format != "text")

    if output_format == "plan":
        from rrr.output import PlanRenderer

        click.echo(PlanRenderer().render(result))
    elif output_format == "markdown":
        from rrr.output import MarkdownRenderer

        click.echo(MarkdownRenderer().render(result))
    elif output_format == "html":
        from rrr.output import HtmlRenderer

        click.echo(HtmlRenderer().render(result))
    elif verbose or output_format == "json":
        # --verbose is the legacy flag for JSON; --format json is the explicit form.
        click.echo(result.model_dump_json(indent=2))
    else:
        conf = (
            f"  CONFIDENCE: {result.aggregate_confidence:.0%}"
            if result.aggregate_confidence is not None
            else ""
        )
        tier_label = f"  TIER: {result.tier.value.upper()}" if result.tier is not None else ""
        sub = ""
        if result.ship_safety_score is not None or result.delivery_performance_score is not None:
            ship = (
                f"  SHIP-SAFETY: {result.ship_safety_score}"
                if result.ship_safety_score is not None
                else ""
            )
            delivery = (
                f"  DELIVERY: {result.delivery_performance_score}"
                if result.delivery_performance_score is not None
                else ""
            )
            sub = ship + delivery
        click.echo(f"VERDICT: {result.verdict.value}  SCORE: {result.score}{conf}{tier_label}{sub}")
    sys.exit(_EXIT_CODES.get(result.verdict, _ERROR_EXIT))


def _cmd_list_releases(
    config_path: str | None,
    value_stream: str | None,
    programme: str | None,
) -> None:
    """Print releases from the brain file, optionally filtered by programme code.

    Each line shows the programme tag, the release name, and — for enabler releases
    that are prerequisites for another release — the dependency annotation.
    """
    from rrr.tools import RKTBrainReader

    try:
        config = ConfigLoader.load(config_path)
    except RRRError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(_ERROR_EXIT)

    vs = value_stream or config.sources.brain.value_stream
    reader = RKTBrainReader(config.sources.brain.dir)
    try:
        records = reader.list_releases(vs, programme=programme)
    except RRRError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(_ERROR_EXIT)

    prog_label = f" — programme: {programme}" if programme else ""
    click.echo(f"Releases in '{vs}'{prog_label} ({len(records)} total):")

    for rec in records:
        tag = f"[{rec.programme}]"
        if rec.release_relationship is not None:
            rel = rec.release_relationship
            suffix = f"  → dependency for {rel.dependency_for} | enables: {rel.enables_release}"
        else:
            suffix = ""
        click.echo(f"  {tag:<10} {rec.ir_name}{suffix}")


if __name__ == "__main__":
    main()
