"""``coffer config list|get|set|unset`` — the settings read before the daemon binds.

One key registry (``_config_keys``) holds them: today the daemon's port, which
must be changeable when the daemon cannot start. Every other setting is a
control on the Settings page (spec resource-framework "Offer every
management operation on the command line"). A value is checked against its
key's type before anything is written; ``unset`` returns a key to its default.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli._config_keys import listing, lookup
from coffer.surfaces.cli._config_registry import Setting, SettingValueError, show
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Read and change Coffer's settings (the keys read before the daemon starts)")
_console = Console()


def _setting(key: str) -> Setting:
    setting = lookup(key)
    if setting is None:
        typer.echo(f"unknown setting {key!r} — run: coffer config list", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    return setting


def _row(setting: Setting) -> dict[str, Any]:
    reading = setting.read()
    row: dict[str, Any] = {
        "key": setting.key,
        "value": reading.value,
        "default": reading.default if reading.has_default else None,
        "has_default": reading.has_default,
        "type": setting.type,
        "help": setting.help,
        "store": setting.store,
    }
    if reading.note:
        row["note"] = reading.note
    return row


@app.command("list")
def list_cmd(
    prefix: str = typer.Argument("", help="Only keys starting with this, e.g. daemon."),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every key with its value, its default, its type and its help."""
    settings = listing(prefix)
    if not settings:
        typer.echo(f"no setting key starts with {prefix!r}", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    rows = [_row(st) for st in settings]
    if output_json:
        typer.echo(_json.dumps({"settings": rows}, indent=2))
        return
    if not rows:
        return
    table = Table(title="Settings")
    for col in ("Key", "Value", "Default", "Type", "Help"):
        table.add_column(col)
    for row in rows:
        value = show(row["value"]) + (f" ({row['note']})" if row.get("note") else "")
        default = show(row["default"]) if row["has_default"] else "(none)"
        table.add_row(row["key"], value, default, row["type"], row["help"])
    _console.print(table)


@app.command("get")
def get_cmd(
    key: str = typer.Argument(..., help="Setting key"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Print a setting's current value."""
    reading = _setting(key).read()
    if output_json:
        body = {
            "key": key,
            "value": reading.value,
            "default": reading.default if reading.has_default else None,
            **reading.extra,
        }
        typer.echo(_json.dumps(body, indent=2))
        return
    for line in reading.lines or [show(reading.value)]:
        typer.echo(line)


@app.command("set")
def set_cmd(
    key: str = typer.Argument(..., help="Setting key"),
    value: str = typer.Argument(..., help="New value (see the key's type in config list)"),
) -> None:
    """Change a setting; the value is checked against the key's type first."""
    setting = _setting(key)
    try:
        parsed = setting.parse(value)
    except SettingValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
    lines = setting.write(parsed)
    for line in lines:
        typer.echo(line)


@app.command("unset")
def unset_cmd(
    key: str = typer.Argument(..., help="Setting key"),
) -> None:
    """Return a setting to its default."""
    lines = _setting(key).unset()
    for line in lines:
        typer.echo(line)
