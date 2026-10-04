"""``coffer path logs`` — where the daemon's log files live.

When the daemon will not start, the log files are what is left to read, so this
names them without a daemon: the log directory and the ``daemon.log`` in it
(``COFFER_LOG_DIR`` moves both). It creates and changes nothing (spec
resource-framework "Keep the command line to what needs it"). Every other file
Coffer keeps is a path the Settings page or a hand-off prompt already names.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from coffer.infrastructure.logging.files import log_dir

app = typer.Typer(help="Where Coffer's log files live")


def _abs(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


@app.command("logs")
def logs(
    output_json: bool = typer.Option(False, "--json", help="JSON object keyed by name"),
) -> None:
    """The log directory and the daemon.log in it (COFFER_LOG_DIR moves both)."""
    directory = _abs(log_dir())
    paths = {"logs": directory, "daemon_log": str(Path(directory) / "daemon.log")}
    if output_json:
        typer.echo(_json.dumps(paths, indent=2))
        return
    for value in paths.values():
        typer.echo(value)
