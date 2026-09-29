"""``coffer config list|get|set|unset`` — every Coffer setting through one command.

One key registry (``_config_keys``) replaces the per-setting subcommands that
grew under ``daemon``, ``engine``, ``provider``, ``retention`` and
``credentials`` (spec resource-framework "Change every setting through one
key-value command"). A value is checked against its key's type before anything
is written; ``unset`` returns a key to its default, and a key with no default
refuses it and says how the key is changed instead.
"""

from __future__ import annotations

import json as _json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli._config_keys import listing, lookup
from coffer.surfaces.cli._config_registry import Session, Setting, SettingValueError, show
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Read and change Coffer's settings (coffer config list shows every key)")
_console = Console()


@contextmanager
def _session(ctx: typer.Context) -> Iterator[Session]:
    s = Session(verbose=bool((ctx.obj or {}).get("verbose", False)))
    try:
        yield s
    finally:
        s.close()


def _setting(s: Session, key: str) -> Setting:
    setting = lookup(s, key)
    if setting is None:
        typer.echo(f"unknown setting {key!r} — run: coffer config list", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    return setting


def _row(s: Session, setting: Setting) -> dict[str, Any]:
    reading = setting.read(s)
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
    ctx: typer.Context,
    prefix: str = typer.Argument("", help="Only keys starting with this, e.g. engine."),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every key with its value, its default, its type and its help."""
    with _session(ctx) as s:
        settings = listing(s, prefix)
        if not settings:
            typer.echo(f"no setting key starts with {prefix!r}", err=True)
            raise typer.Exit(int(ExitCode.NOT_FOUND))
        rows = [_row(s, st) for st in settings]
    if output_json:
        typer.echo(_json.dumps({"settings": rows}, indent=2))
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
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting key"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Print a setting's current value."""
    with _session(ctx) as s:
        setting = _setting(s, key)
        reading = setting.read(s)
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
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting key"),
    value: str = typer.Argument(..., help="New value (see the key's type in config list)"),
) -> None:
    """Change a setting; the value is checked against the key's type first."""
    with _session(ctx) as s:
        setting = _setting(s, key)
        try:
            parsed = setting.parse(value)
        except SettingValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
        lines = setting.write(s, parsed)
    for line in lines:
        typer.echo(line)


@app.command("unset")
def unset_cmd(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting key"),
) -> None:
    """Return a setting to its default."""
    with _session(ctx) as s:
        setting = _setting(s, key)
        if setting.unset is None:
            typer.echo(setting.unset_hint, err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        lines = setting.unset(s)
    for line in lines:
        typer.echo(line)
