"""Desktop-app operations started from the command line.

Spec secret "Approve from the command line with the person's own presence
check" and desktop-app "Serve the command line's desktop requests". Revealing a
secret and writing a master key backup take the person's presence check, and
what they produce stays in the app: the value is shown in the Coffer window and
the backup's passphrase is typed there. A reveal's and a backup's command
learn whether the person went through with it — a backup's with the path the
file was written to; the import command learns only that the app opened it.
The updater lives in the app as well, so the update commands are requests to
it too.
"""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _desktop, _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

secrets = group("secret")
updates = group("app update")

_TIMEOUT = typer.Option(120.0, "--timeout", help="Seconds to wait for the app and the person")
_NO_LAUNCH = typer.Option(False, "--no-launch", help="Do not start the desktop app")


def _ended(request: dict[str, Any], done: str, *, as_json: bool) -> None:
    _io.emit(
        {
            "status": request["status"],
            "message": request.get("message"),
            "result": request.get("result"),
        },
        as_json=as_json,
        human=lambda r: typer.echo(
            done if r["status"] == "done" else f"not done: {r['message'] or r['status']}"
        ),
    )
    if request["status"] != "done":
        raise typer.Exit(int(ExitCode.PRESENCE_NOT_CONFIRMED))


@secrets.command("reveal")
@maps("secret reveal", ("POST", "/desktop/requests"), ui="Secrets · Reveal (desktop app, Touch ID)")
def reveal(
    ref: str = typer.Argument(..., help="The secret's ref (coffer secret list)"),
    timeout: float = _TIMEOUT,
    no_launch: bool = _NO_LAUNCH,
    as_json: bool = _io.json_option(),
) -> None:
    """Show a secret's value to the person, in the Coffer window, after Touch ID.

    The value never reaches this command, its output or any log.
    """
    request = _desktop.run(
        {"op": "reveal", "ref": ref}, as_json=as_json, timeout=timeout, launch=not no_launch
    )
    _ended(request, "shown in the Coffer app", as_json=as_json)


@secrets.command("backup-key")
@maps(
    "secret backup-key",
    ("POST", "/desktop/requests"),
    ui="Settings · Secrets · Back up the master key (desktop app, Touch ID)",
)
def backup_key(
    timeout: float = typer.Option(600.0, "--timeout", help="Seconds to wait for the person"),
    no_launch: bool = _NO_LAUNCH,
    as_json: bool = _io.json_option(),
) -> None:
    """Open the master key backup in the Coffer app; the person checks presence,
    types the passphrase and picks the folder there.

    Waits until the person has written the backup, then prints where (exit 0);
    closing the dialog, or no backup by --timeout, exits 11 with nothing
    written. The path is the one the daemon wrote, reported by the app."""
    request = _desktop.run(
        {"op": "export_master_key"}, as_json=as_json, timeout=timeout, launch=not no_launch
    )
    written = (request.get("result") or {}).get("path")
    if request["status"] == "done" and not written:
        # Only a written file counts: an app that reports done with no path
        # (one that predates this report) has opened the dialog, nothing more.
        request = {
            **request,
            "status": "failed",
            "message": "the app did not report a written backup; check it in the Coffer app",
        }
    _ended(request, f"the backup was written to {written}", as_json=as_json)


@secrets.command("import-key")
@maps(
    "secret import-key",
    ("POST", "/desktop/requests"),
    ui="Settings · Security · Import a master key (desktop app, Touch ID)",
)
def import_key(
    timeout: float = typer.Option(600.0, "--timeout", help="Seconds to wait for the person"),
    no_launch: bool = _NO_LAUNCH,
    as_json: bool = _io.json_option(),
) -> None:
    """Open the master key import in the Coffer app; the person picks the backup
    file, types its passphrase and checks presence there."""
    request = _desktop.run(
        {"op": "import_master_key"}, as_json=as_json, timeout=timeout, launch=not no_launch
    )
    _ended(request, "opened the master key import in the Coffer app", as_json=as_json)


def _update(op: str, *, as_json: bool, enabled: bool | None = None, timeout: float = 60.0) -> None:
    body: dict[str, Any] = {"op": op}
    if enabled is not None:
        body["enabled"] = enabled
    request = _desktop.run(body, as_json=as_json, timeout=timeout)
    _io.emit(request.get("result") or {"status": request["status"]}, as_json=as_json)
    if request["status"] != "done":
        _io.fail(
            "CLI_DESKTOP_REQUEST_FAILED",
            request.get("message") or request["status"],
            ExitCode.GENERIC,
            as_json=as_json,
        )


@updates.command("status")
@maps("app update status", ("POST", "/desktop/requests"), ui="Settings · About · update status")
def update_status(as_json: bool = _io.json_option()) -> None:
    """The app's version, the newest release found and whether it checks daily."""
    _update("update_status", as_json=as_json)


@updates.command("check")
@maps("app update check", ("POST", "/desktop/requests"), ui="Settings · About · Check for updates")
def update_check(as_json: bool = _io.json_option()) -> None:
    """Check for a new release against the signed manifest now."""
    _update("update_check", as_json=as_json)


@updates.command("install")
@maps(
    "app update install", ("POST", "/desktop/requests"), ui="Settings · About · Install and restart"
)
def update_install(as_json: bool = _io.json_option()) -> None:
    """Download, verify and install the release found, then restart the app."""
    _update("update_install", as_json=as_json, timeout=600.0)


@updates.command("auto-check")
@maps(
    "app update auto-check",
    ("POST", "/desktop/requests"),
    ui="Settings · About · check automatically",
)
def update_auto_check(
    state: str = typer.Argument(..., help="on or off"), as_json: bool = _io.json_option()
) -> None:
    """Switch the app's daily update check on or off."""
    if state not in ("on", "off"):
        _io.fail("CLI_INVALID_INPUT", "say on or off", ExitCode.INVALID_INPUT, as_json=as_json)
    _update("update_auto_check", as_json=as_json, enabled=state == "on")


__all__ = ["secrets", "updates"]
