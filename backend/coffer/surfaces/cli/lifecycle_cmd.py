"""``coffer update`` and ``coffer uninstall`` — upgrade or remove Coffer on this
machine (spec daemon "Upgrade the installed binaries from the command line" and
"Uninstall Coffer from this machine").

How Coffer was installed decides how each runs. The running daemon reports it
(``GET /daemon/upgrade``): the desktop app's daemon hands both to the app — its
signed updater, its uninstall dialog with Touch ID — and the installer's
binaries are upgraded and removed here. Everything this module needs is
imported up front: an uninstall deletes the binary this process was started
from.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import typer

import coffer
from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon.binary_update import UpdateError, apply_release
from coffer.infrastructure.daemon.data_purge import purge_data
from coffer.infrastructure.daemon.release_check import Release, fetch_latest_sync, is_newer
from coffer.infrastructure.daemon.spawn import spawn_detached_daemon
from coffer.infrastructure.platform.process import executable_name
from coffer.infrastructure.vault.home import bin_dir, coffer_home, daemon_json_path
from coffer.surfaces.cli import _desktop, _io
from coffer.surfaces.cli import daemon_cmd as _daemon
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.registry import maps

#: What ``--delete-data`` asks to be typed.
DELETE_PHRASE = "delete my data"
#: How long the daemon may take to stop after its uninstall answered.
_EXIT_WAIT_SECONDS = 20.0

_STEP_LABELS = {
    "agents": "list the agents",
    "provider_routing": "take Coffer's model routing out of the agents",
    "agent_connections": "disconnect the agents",
    "skill_links": "remove the skill links",
    "login_job": "turn off start at login",
    "terminal_files": "remove terminal launch files",
    "path_lines": "remove the installer's PATH lines",
    "binaries": "remove ~/.coffer/bin",
}


def _install_method(*, as_json: bool) -> str:
    return str(_io.call("GET", "/daemon/upgrade", as_json=as_json)["install_method"])


def _restart_from_bin(*, as_json: bool) -> None:
    """Stop the daemon and start the one just installed in ``~/.coffer/bin``."""
    _daemon._stop_daemon()
    daemon = bin_dir() / executable_name("coffer-daemon")
    try:
        proc = spawn_detached_daemon(command=[str(daemon)])
    except OSError as exc:
        _io.fail(
            "CLI_UPDATE_RESTART",
            f"could not start {daemon}: {exc}",
            ExitCode.GENERIC,
            as_json=as_json,
        )
    if _daemon._wait_until_serving(proc) != "serving":
        _io.fail(
            "CLI_UPDATE_RESTART",
            "the new daemon did not come up; check ~/.coffer/logs/daemon.log",
            ExitCode.GENERIC,
            as_json=as_json,
        )


def _release_line(release: Release) -> str:
    return f"Coffer {release.version} is available (you have {coffer.__version__}): {release.url}"


@maps(
    "update",
    ("GET", "/daemon/upgrade"),
    ui="Settings · About · Check for updates (installer binaries)",
)
def update(
    check: bool = typer.Option(False, "--check", help="Only say whether a newer release exists"),
    as_json: bool = _io.json_option(),
) -> None:
    """Upgrade Coffer to the newest release and restart the daemon on it.

    The installer's binaries are downloaded, checked against the release's
    SHA256SUMS and swapped in place; the desktop app installs its own signed
    update; a source checkout is upgraded with git."""
    method = _install_method(as_json=as_json)
    if method == "app":
        request = _desktop.run(
            {"op": "update_check" if check else "update_install"},
            as_json=as_json,
            timeout=60.0 if check else 600.0,
        )
        _io.emit(request.get("result") or {"status": request["status"]}, as_json=as_json)
        if request["status"] != "done":
            _io.fail(
                "CLI_DESKTOP_REQUEST_FAILED",
                request.get("message") or request["status"],
                ExitCode.GENERIC,
                as_json=as_json,
            )
        return
    if method == "source":
        message = (
            "this Coffer runs from a source checkout: upgrade it with `git pull`, reinstall "
            "the backend and the frontend, then `coffer daemon restart` "
            "(https://wyx-sg.github.io/Coffer/start/install#upgrade)"
        )
        if check:
            _io.emit({"install_method": method, "message": message}, as_json=as_json)
            return
        _io.fail("CLI_UPDATE_SOURCE", message, ExitCode.INVALID_USAGE, as_json=as_json)
    try:
        release = fetch_latest_sync()
    except Exception as exc:
        _io.fail(
            "CLI_UPDATE_CHECK_FAILED",
            f"could not read the latest release: {exc}",
            ExitCode.GENERIC,
            as_json=as_json,
        )
    newer = is_newer(release.version, coffer.__version__)
    result: dict[str, Any] = {
        "running": coffer.__version__,
        "latest": release.version,
        "available": newer,
        "url": release.url,
    }
    if check or not newer:
        _io.emit(
            result,
            as_json=as_json,
            human=lambda r: typer.echo(
                _release_line(release)
                if r["available"]
                else f"Coffer {coffer.__version__} is the newest release"
            ),
        )
        return
    if not as_json:
        typer.echo(f"downloading Coffer {release.version}…")
    try:
        apply_release(release, bin_dir())
    except (UpdateError, OSError) as exc:
        _io.fail("CLI_UPDATE_FAILED", str(exc), ExitCode.GENERIC, as_json=as_json)
    except Exception as exc:
        _io.fail(
            "CLI_UPDATE_FAILED", f"the download failed: {exc}", ExitCode.GENERIC, as_json=as_json
        )
    _restart_from_bin(as_json=as_json)
    _io.emit(
        {**result, "installed": release.version},
        as_json=as_json,
        human=lambda _r: typer.echo(f"Coffer {release.version} installed; the daemon runs it"),
    )


def _confirm_at_terminal(prompt: str, answer: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() == answer
    except EOFError:
        return False


def _wait_for_exit() -> bool:
    deadline = time.monotonic() + _EXIT_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not daemon_json_path().exists() and bootstrap.live_daemon() is None:
            return True
        time.sleep(0.2)
    return False


def _print_steps(answer: dict[str, Any]) -> None:
    for step in answer["steps"]:
        label = _STEP_LABELS.get(step["key"], step["key"])
        mark = {"done": "✓", "nothing": "·", "failed": "✗"}.get(step["outcome"], "?")
        detail = f" — {step['detail']}" if step.get("detail") else ""
        typer.echo(f"{mark} {label}{detail}")


@maps(
    "uninstall",
    ("POST", "/daemon/uninstall"),
    ui="Settings · About · Uninstall Coffer (desktop app)",
)
def uninstall(
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before uninstalling"),
    delete_data: bool = typer.Option(
        False,
        "--delete-data",
        help=f"Also delete ~/.coffer and the master key; asks for '{DELETE_PHRASE}' "
        "at a terminal, whatever else is given",
    ),
    as_json: bool = _io.json_option(),
) -> None:
    """Remove Coffer from this Mac: disconnect the agents, remove the skill links,
    start at login, the binaries and the installer's PATH lines, then stop the
    daemon. ~/.coffer stays unless --delete-data.

    With the desktop app, this opens its uninstall dialog, where you confirm."""
    method = _install_method(as_json=as_json)
    if method == "app":
        request = _desktop.run(
            {"op": "uninstall", "enabled": delete_data}, as_json=as_json, timeout=60.0
        )
        if request["status"] != "done":
            _io.fail(
                "CLI_DESKTOP_REQUEST_FAILED",
                request.get("message") or request["status"],
                ExitCode.GENERIC,
                as_json=as_json,
            )
        _io.emit(
            {"status": "opened", "where": "Coffer app"},
            as_json=as_json,
            human=lambda _r: typer.echo("opened Uninstall Coffer in the Coffer app; confirm there"),
        )
        return
    home = coffer_home()
    if delete_data:
        if not _confirm_at_terminal(
            f"This deletes {home} — every secret, skill, knowledge collection and the master "
            f"key — for good.\nType '{DELETE_PHRASE}' to uninstall and delete it: ",
            DELETE_PHRASE,
        ):
            _io.fail(
                "CLI_UNINSTALL_NOT_CONFIRMED",
                f"deleting the data needs '{DELETE_PHRASE}' typed at a terminal; "
                "nothing was removed",
                ExitCode.INVALID_USAGE,
                as_json=as_json,
            )
    elif not yes and not _confirm_at_terminal(
        f"Uninstall Coffer from this Mac? {home} stays. [y/N] ", "y"
    ):
        _io.fail(
            "CLI_UNINSTALL_NOT_CONFIRMED",
            "not confirmed (run with --yes where there is no terminal); nothing was removed",
            ExitCode.INVALID_USAGE,
            as_json=as_json,
        )
    answer = _io.call("POST", "/daemon/uninstall", as_json=as_json, body={}, timeout=120.0)
    stopped = _wait_for_exit()
    purge: dict[str, Any] | None = None
    if delete_data:
        if not stopped:
            _io.fail(
                "CLI_UNINSTALL_DAEMON_RUNNING",
                f"the daemon did not stop, so {home} was not deleted; "
                "stop it and delete it by hand",
                ExitCode.GENERIC,
                as_json=as_json,
            )
        result = purge_data()
        purge = {"removed": result.removed, "kept": result.kept, "errors": result.errors}
    out = {**answer, "daemon_stopped": stopped, "purge": purge, "install_method": method}

    def human(_r: dict[str, Any]) -> None:
        _print_steps(answer)
        if not stopped:
            typer.echo("! the daemon did not stop; run `coffer daemon stop`")
        if purge is not None:
            for removed in purge["removed"]:
                typer.echo(f"✓ deleted {removed}")
            for kept in purge["kept"]:
                typer.echo(f"· your moved vault at {kept} was left in place")
            for error in purge["errors"]:
                typer.echo(f"✗ {error}")
        if method == "source":
            typer.echo("this was a source install: remove the checkout and its .venv yourself")
        typer.echo("Coffer is uninstalled. Open shells keep the old PATH until they restart.")

    _io.emit(out, as_json=as_json, human=human)
    if not answer["ok"] or (purge is not None and purge["errors"]):
        raise typer.Exit(int(ExitCode.GENERIC))


__all__ = ["DELETE_PHRASE", "uninstall", "update"]
