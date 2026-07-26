"""``rrr-ingest`` CLI entry point — converts RKT HTML reports to brain contract JSON.

Usage:
    rrr-ingest --html-dir input --brain-dir brain --value-stream "Retirement-Services"

Each ``.html`` file in ``--html-dir`` becomes one dated snapshot in
``<brain-dir>/<value-stream>-history.json``.  Running the same file again is safe
(idempotent upsert on the snapshot date).  See ADR-0018 for the field mapping.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from rrr.ingest.brain_writer import BrainWriter
from rrr.ingest.html_extractor import HTMLExtractor


@click.command()
@click.option(
    "--html-dir",
    "html_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Directory containing RKT Program Metrics HTML report(s).",
)
@click.option(
    "--brain-dir",
    "brain_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Output directory for brain contract JSON files (created if absent).",
)
@click.option(
    "--value-stream",
    "value_stream",
    required=True,
    help="Value-stream name used as the brain file prefix (e.g. 'Retirement-Services').",
)
@click.option("--verbose", is_flag=True, help="Enable DEBUG logging.")
def ingest(html_dir: Path, brain_dir: Path, value_stream: str, verbose: bool) -> None:
    """Convert RKT HTML report(s) in HTML_DIR to a brain contract history file."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s  %(name)s — %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("rrr.ingest")

    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        click.echo(f"No .html files found in {html_dir}", err=True)
        sys.exit(1)

    extractor = HTMLExtractor()
    writer = BrainWriter()
    processed = 0

    for html_path in html_files:
        log.info("Processing %s", html_path.name)
        try:
            date, releases = extractor.extract(html_path)
        except (ValueError, KeyError) as exc:
            # Not a valid RKT report — skip and warn rather than aborting the batch.
            click.echo(f"  SKIP  {html_path.name}  —  {exc}", err=True)
            continue

        out_path = writer.append_snapshot(brain_dir, value_stream, date, releases)
        click.echo(
            f"  OK    {html_path.name}  →  snapshot {date}  ({len(releases)} releases)"
            f"  →  {out_path}"
        )
        processed += 1

    if processed == 0:
        click.echo(
            f"ERROR: No valid RKT Program Metrics reports found in {html_dir} "
            f"({len(html_files)} file(s) checked — all skipped).",
            err=True,
        )
        sys.exit(1)

    out_file = brain_dir / f"{value_stream}-history.json"
    click.echo(f"\nDone: {processed} of {len(html_files)} file(s) ingested into {out_file}")


if __name__ == "__main__":
    ingest()
