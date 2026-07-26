"""Click entry point for the RRR web dashboard (``rrr-ui`` command, ADR-0020).

Validates the config, checks that NiceGUI is installed (fails with a clear
install instruction if not), then delegates to ``run_ui()`` in ``app.py``.
The server runs until the user presses Ctrl-C.

Dataset selection is automatic (ADR-0022): ``run_ui()`` scans ``brain/`` for
``*-history.json`` files.  When multiple files exist a picker appears in the
page header.  No ``--value-stream`` argument is required.

Usage:
    rrr-ui [--config PATH] [--port N] [--host HOST]
"""

from __future__ import annotations

import sys

import click

from rrr.config import ConfigLoader
from rrr.errors import RRRError


@click.command("rrr-ui")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Optional config YAML; merged over bundled defaults.",
)
@click.option(
    "--port",
    default=8080,
    show_default=True,
    help="TCP port for the web server.",
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Network interface to bind (127.0.0.1 = local only).",
)
@click.option(
    "--no-browser",
    "no_browser",
    is_flag=True,
    default=False,
    help="Do not open a browser tab automatically on startup.",
)
def ui_main(
    config_path: str | None,
    port: int,
    host: str,
    no_browser: bool,
) -> None:
    """Start the RRR web dashboard (NiceGUI, local-first on http://HOST:PORT)."""
    try:
        import nicegui  # noqa: F401
    except ImportError:
        click.echo(
            'ERROR: NiceGUI is not installed.  Run:\n    pip install "rrr[ui]"\nthen try again.',
            err=True,
        )
        sys.exit(3)

    try:
        config = ConfigLoader.load(config_path)
    except RRRError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(3)

    from rrr.ui.app import run_ui

    click.echo(f"Starting RRR Dashboard at http://{host}:{port}  (Ctrl-C to stop)")
    run_ui(config, host=host, port=port, show=not no_browser)
