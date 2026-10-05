"""``coffer path logs`` and ``coffer path skill-data`` — two directories to name.

When the daemon will not start, the log files are what is left to read, so this
names them without a daemon: the log directory and the ``daemon.log`` in it
(``COFFER_LOG_DIR`` moves both). It creates and changes nothing (spec
resource-framework "Offer every management operation on the command line"). ``skill-data`` names
``~/.coffer/skill-data``, where a skill's scripts keep their logs, operation
journals and temp files (one ``<skill-name>/`` folder each; never synced, pruned
by the ``skill_data`` retention policy), so a script finds it without guessing.
Every other file Coffer keeps is a path the Settings page or a hand-off prompt
already names.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.vault.home import skill_data_dir

app = typer.Typer(help="Where Coffer's log files and skill working files live")


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


@app.command("skill-data")
def skill_data(
    output_json: bool = typer.Option(False, "--json", help="JSON object keyed by name"),
) -> None:
    """The directory skill scripts write logs, journals and temp files under."""
    directory = _abs(skill_data_dir())
    if output_json:
        typer.echo(_json.dumps({"skill_data": directory}, indent=2))
        return
    typer.echo(directory)
