"""``rrr-collect`` CLI — interactive data collection for RRR dimension JSON files (ADR-0023).

Entry point: ``rrr-collect [OPTIONS]``

Collects dimension-specific data files (``data/<dimension>.json``) needed before
running ``rrr --release <name>``. Three modes of operation:

  --status           Print a per-dimension traffic-light (fresh / stale / missing) and exit.
  --dimension DIM    Collect one named dimension interactively.
  --all              Collect all dimensions registered for the given tier.

Tier controls which dimensions are required. Hotfix tier skips non-critical
gate dimensions (e.g. accessibility). Standard is the default.

All collection is interactive, driven by ``InteractiveCollector``. Adapters (K6, Snyk,
SonarQube) exist in ``collectors/adapters/`` and can be invoked programmatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from rrr.collectors.interactive import InteractiveCollector
from rrr.collectors.registry import CollectorRegistry
from rrr.collectors.runner import CollectorRunner, CollectorStatus

# Emoji-free traffic-light symbols for terminal output.
_STATUS_ICON = {
    CollectorStatus.FRESH: "[FRESH ]",
    CollectorStatus.STALE: "[STALE ]",
    CollectorStatus.MISSING: "[MISSING]",
}

_DEFAULT_DATA_DIR = "data"
_DEFAULT_TIER = "standard"

# Dimensions excluded for hotfix tier (non-critical gate-only dimensions).
_HOTFIX_EXCLUDED: frozenset[str] = frozenset(
    {"accessibility", "architecture_fitness", "architecture_drift"}
)


@click.command(name="rrr-collect")
@click.option(
    "--release", "-r",
    default=None,
    help="Release name (IR name). Required for --dimension and --all.",
)
@click.option(
    "--tier",
    type=click.Choice(["hotfix", "standard", "major"], case_sensitive=False),
    default=_DEFAULT_TIER,
    show_default=True,
    help="Release risk tier — controls which dimensions are required.",
)
@click.option(
    "--dimension", "-d",
    "dimension",
    default=None,
    help="Collect one named dimension interactively.",
)
@click.option(
    "--all", "all_dims",
    is_flag=True,
    default=False,
    help="Collect all dimensions registered for the given tier.",
)
@click.option(
    "--status",
    "show_status",
    is_flag=True,
    default=False,
    help="Print per-dimension freshness status and exit.",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Overwrite existing files even when they are FRESH.",
)
@click.option(
    "--skip-optional",
    is_flag=True,
    default=False,
    help="Accept defaults for non-required (Optional) fields without prompting.",
)
@click.option(
    "--data-dir",
    default=_DEFAULT_DATA_DIR,
    show_default=True,
    help="Directory to read from and write ``<dimension>.json`` files to.",
)
def cli(
    release: str | None,
    tier: str,
    dimension: str | None,
    all_dims: bool,
    show_status: bool,
    refresh: bool,
    skip_optional: bool,
    data_dir: str,
) -> None:
    """Collect dimension data files for an RRR assessment.

    Run ``rrr-collect --status`` to see which data files are fresh, stale, or
    missing before running ``rrr --release <name>``.
    """
    registry = CollectorRegistry()
    runner = CollectorRunner()
    data_path = Path(data_dir)

    if show_status:
        _run_status(registry, runner, data_path, tier)
        return

    if not release:
        click.echo("Error: --release is required for --dimension and --all.", err=True)
        sys.exit(1)

    if all_dims:
        _run_all(registry, runner, release, tier, data_path, refresh, skip_optional)
        return

    if dimension:
        _run_one(registry, runner, dimension, release, data_path, refresh, skip_optional)
        return

    # No mode selected — show help-like message.
    click.echo("Specify --status, --dimension DIM, or --all. Use --help for details.", err=True)
    sys.exit(1)


def _active_dimensions(registry: CollectorRegistry, tier: str) -> list[str]:
    """Return the ordered list of dimensions active for this tier.

    Hotfix tier excludes non-critical gate-only dimensions that are not
    applicable to emergency fixes (accessibility, architecture checks).
    """
    dims = registry.dimensions()
    if tier == "hotfix":
        return [d for d in dims if d not in _HOTFIX_EXCLUDED]
    return dims


def _run_status(
    registry: CollectorRegistry,
    runner: CollectorRunner,
    data_path: Path,
    tier: str,
) -> None:
    """Print a per-dimension freshness table and exit.

    Exits with code 0 if all active dimensions are FRESH, 2 if any are STALE
    or MISSING (so CI scripts can detect incomplete data).
    """
    dims = _active_dimensions(registry, tier)
    reports = runner.status(dims, data_path)

    click.echo(f"\nData freshness status (tier: {tier}, data-dir: {data_path})\n")
    any_bad = False
    for report in reports:
        icon = _STATUS_ICON[report.status]
        age = f"  {report.age_days:.1f}d old" if report.age_days is not None else ""
        click.echo(f"  {icon}  {report.dimension}{age}")
        if report.status != CollectorStatus.FRESH:
            any_bad = True

    click.echo()
    if any_bad:
        click.echo("Run rrr-collect --release <name> --all to populate missing/stale files.")
        sys.exit(2)


def _run_one(
    registry: CollectorRegistry,
    runner: CollectorRunner,
    dimension: str,
    release: str,
    data_path: Path,
    refresh: bool,
    skip_optional: bool,
) -> None:
    """Collect one dimension interactively, respecting the --refresh flag."""
    if not registry.is_registered(dimension):
        click.echo(
            f"Error: dimension {dimension!r} is not registered. "
            f"Known dimensions: {', '.join(registry.dimensions())}",
            err=True,
        )
        sys.exit(1)

    if not refresh:
        reports = runner.status([dimension], data_path)
        if reports[0].status == CollectorStatus.FRESH:
            click.echo(f"  {dimension}: already FRESH — use --refresh to overwrite.")
            return

    from rrr.collectors.base import CollectorConfig

    model_class = registry.model_for(dimension)
    collector = InteractiveCollector(dimension, model_class)
    config = CollectorConfig(release=release, data_dir=data_path, skip_optional=skip_optional)

    result = runner.run(dimension, collector, config, model_class)
    click.echo(f"\n  Wrote {data_path / dimension}.json (captured_at: {result.collected_at})")


def _run_all(
    registry: CollectorRegistry,
    runner: CollectorRunner,
    release: str,
    tier: str,
    data_path: Path,
    refresh: bool,
    skip_optional: bool,
) -> None:
    """Collect all active dimensions for the given tier, skipping FRESH ones unless --refresh."""
    from rrr.collectors.base import CollectorConfig

    dims = _active_dimensions(registry, tier)
    reports = {r.dimension: r for r in runner.status(dims, data_path)}

    for dim in dims:
        report = reports.get(dim)
        if not refresh and report and report.status == CollectorStatus.FRESH:
            click.echo(f"\n  {dim}: already FRESH — skipping (use --refresh to overwrite)")
            continue

        model_class = registry.model_for(dim)
        collector = InteractiveCollector(dim, model_class)
        config = CollectorConfig(release=release, data_dir=data_path, skip_optional=skip_optional)

        result = runner.run(dim, collector, config, model_class)
        click.echo(f"\n  Wrote {data_path / dim}.json (captured_at: {result.collected_at})")
