"""`coffer migrate`: the one-time upgrade of this home to the vault layout,
its rollback, and a rehearsal of both on a copy.

It runs in this process with the daemon stopped — the daemon refuses to start
on a home that still holds only ``coffer.db``, and this command refuses to run
while a daemon is up — because the upgrade moves the trees and the database
the daemon holds open. The steps and the rollback rules are
``coffer.infrastructure.vault.migration``'s.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from coffer import __version__
from coffer.domain.error_base import CofferError
from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.persistence.migrations_runner import upgrade_to
from coffer.infrastructure.vault.migration.rehearse import rehearse
from coffer.infrastructure.vault.migration.rollback import resume, rollback
from coffer.infrastructure.vault.migration.run import migrate
from coffer.surfaces.cli._options import ExitCode


def _home() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser()


def _refuse_if_the_daemon_is_up() -> None:
    running = bootstrap.live_daemon()
    if running is not None:
        typer.echo(
            f"a Coffer daemon is running (pid {running.pid}); stop it with "
            "`coffer daemon stop` first",
            err=True,
        )
        raise typer.Exit(int(ExitCode.CONFLICT))


def _print(lines: list[str]) -> None:
    for line in lines:
        typer.echo(line)


def _rehearse(home: Path) -> None:
    result = rehearse(home, upgrade_db=upgrade_to, build=__version__)
    _print(result.report.lines())
    _print([f"missing after the upgrade: {m}" for m in result.missing])
    _print([f"rollback: {p}" for p in result.rollback_problems])
    _print([f"not restored by the rollback: {m}" for m in result.not_restored])
    if result.report.outcome != "migrated":
        typer.echo("nothing to rehearse: this home has no pre-vault database")
        return
    if not result.ok:
        typer.echo("the rehearsal found problems; do not migrate this home yet", err=True)
        raise typer.Exit(int(ExitCode.GENERIC))
    typer.echo("rehearsal passed: every item survived and the rollback restored the copy")


def migrate_command(
    rollback_: bool = typer.Option(
        False, "--rollback", help="Put this home back as it was before the upgrade."
    ),
    resume_: bool = typer.Option(
        False, "--resume", help="Lift the hold a rollback left, so the upgrade can run again."
    ),
    rehearse_: bool = typer.Option(
        False,
        "--rehearse",
        help="Run the upgrade and its rollback on a copy; the home itself is only read.",
    ),
    home: Path | None = typer.Option(  # noqa: B008
        None, "--home", help="With --rehearse: the home to copy (default: $HOME)."
    ),
) -> None:
    """Move this home out of coffer.db into the vault layout (once, daemon stopped)."""
    chosen = [flag for flag in (rollback_, resume_, rehearse_) if flag]
    if len(chosen) > 1:
        typer.echo("choose one of --rollback, --resume and --rehearse", err=True)
        raise typer.Exit(int(ExitCode.INVALID_USAGE))
    if home is not None and not rehearse_:
        typer.echo("--home only goes with --rehearse", err=True)
        raise typer.Exit(int(ExitCode.INVALID_USAGE))
    try:
        if rehearse_:
            _rehearse((home or _home()).expanduser())
            return
        if resume_:
            lifted = resume(_home())
            typer.echo("hold lifted; run `coffer migrate`" if lifted else "no hold to lift")
            return
        _refuse_if_the_daemon_is_up()
        if rollback_:
            problems = rollback(_home())
            _print([f"left where it is: {p}" for p in problems])
            typer.echo(
                "rolled back; install the previous Coffer build to use this home "
                "(`coffer migrate --resume` to take the upgrade again)"
            )
            return
        report = migrate(_home(), upgrade_db=upgrade_to, build=__version__)
    except CofferError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(int(ExitCode.CONFLICT)) from exc
    _print(report.lines())
    if report.outcome == "migrated":
        typer.echo("migrated; `coffer migrate --rollback` undoes it while the daemon is stopped")


__all__ = ["migrate_command"]
