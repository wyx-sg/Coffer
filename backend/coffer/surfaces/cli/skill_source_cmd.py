"""``coffer skill add <archive|git-url>`` and ``coffer skill update`` (spec
skill-manager "Add skills from an archive", "Add skills from a Git
repository", "Update a Git-imported skill from its source").

Both go through the daemon's staging routes, so the command line sees exactly
what the Add skill dialog sees: the archive is uploaded (``POST
/skills/stage/archive``), the repository cloned into staging (``POST
/skills/stage/git``), and nothing is added until the user answers the prompt
(or passes ``--yes``); a no, or a choice the command cannot make, removes the
stage. ``update`` previews, asks, and applies — refusing a conflict with a
local edit until ``--take-theirs`` or ``--keep-mine`` says which side wins.
"""

from __future__ import annotations

import json as _json
import pathlib
from typing import Any

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_ref

#: Cloning a repository can take a while; the daemon bounds git itself.
_GIT_TIMEOUT_S = 240.0
_ARCHIVE_SUFFIXES = (".zip", ".skill")


def looks_like_git_url(ref: str) -> bool:
    """A URL git can clone, rather than a path on this machine."""
    return "://" in ref or (ref.count(":") == 1 and "@" in ref.split(":", 1)[0])


def looks_like_archive(ref: str) -> bool:
    return ref.lower().endswith(_ARCHIVE_SUFFIXES) and pathlib.Path(ref).expanduser().is_file()


def _describe(skill: dict[str, Any]) -> str:
    name = skill["name"] or skill["folder"]
    if not skill["valid"]:
        return f"  ✗ {name} — {skill['message'] or skill['reason']}"
    mark = " (replaces the existing skill)" if skill["taken"] else ""
    return f"  • {name}{mark} — {skill['description']}"


def _cancel(c: httpx.Client, staging_id: str) -> None:
    c.delete(f"/skills/stage/{staging_id}")


def _choose(stage: dict[str, Any], names: list[str], all_: bool) -> list[str]:
    """The names to add, or an exit with the reason nothing can be chosen."""
    valid = [s for s in stage["skills"] if s["valid"] and s["name"]]
    if names:
        known = {s["name"] for s in valid}
        missing = [n for n in names if n not in known]
        if missing:
            typer.echo(f"not found among the valid skills here: {', '.join(missing)}", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        return list(dict.fromkeys(names))
    if all_:
        chosen = [s["name"] for s in valid]
    elif len(stage["skills"]) == 1 and valid:
        chosen = [valid[0]["name"]]
    else:
        typer.echo(
            "several skills found; choose with --skill <name> (repeatable) or --all", err=True
        )
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    if not chosen:
        typer.echo("no skill here can be added", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    return chosen


def confirm_stage(
    c: httpx.Client,
    stage: dict[str, Any],
    *,
    names: list[str],
    all_: bool,
    yes: bool,
    force: bool,
    verbose: bool,
) -> None:
    """Print what the stage holds, choose, ask, then confirm or cancel it."""
    staging_id = stage["staging_id"]
    typer.echo(
        f"found in {stage['label']}"
        + (f" at {stage['commit'][:7]}" if stage["commit"] else "")
        + ":"
    )
    for skill in stage["skills"]:
        typer.echo(_describe(skill))
    try:
        chosen = _choose(stage, names, all_)
        by_name = {s["name"]: s for s in stage["skills"] if s["name"]}
        taken = [n for n in chosen if by_name[n]["taken"]]
        if taken and not force:
            typer.echo(
                f"already a skill: {', '.join(taken)} — pass --force to replace it", err=True
            )
            raise typer.Exit(int(ExitCode.CONFLICT))
        if not yes and not typer.confirm(f"add {', '.join(chosen)}?", default=False):
            typer.echo("nothing added")
            raise typer.Exit(0)
    except typer.Exit:
        _cancel(c, staging_id)
        raise
    r = c.post(
        f"/skills/stage/{staging_id}/confirm",
        json={"skills": chosen, "replace": taken},
    )
    if r.is_error:
        _cancel(c, staging_id)
    _cli_client.check(r, verbose=verbose)
    for item in r.json()["items"]:
        typer.echo(f"added: skill {item['name']}")


def add_archive(
    ctx: typer.Context, path: str, *, names: list[str], all_: bool, yes: bool, force: bool
) -> None:
    verbose = verbose_of(ctx)
    archive = pathlib.Path(path).expanduser()
    c, _info = _cli_client.client_or_exit()
    with c, archive.open("rb") as fh:
        r = c.post(
            "/skills/stage/archive",
            files={"file": (archive.name, fh, "application/zip")},
            timeout=_GIT_TIMEOUT_S,
        )
        _cli_client.check(r, verbose=verbose)
        confirm_stage(c, r.json(), names=names, all_=all_, yes=yes, force=force, verbose=verbose)


def add_git(
    ctx: typer.Context,
    url: str,
    *,
    ref: str | None,
    subpath: str | None,
    names: list[str],
    all_: bool,
    yes: bool,
    force: bool,
) -> None:
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/skills/stage/git",
            json={"url": url, "ref": ref, "path": subpath},
            timeout=_GIT_TIMEOUT_S,
        )
        _cli_client.check(r, verbose=verbose)
        confirm_stage(c, r.json(), names=names, all_=all_, yes=yes, force=force, verbose=verbose)


def _print_changes(title: str, changes: list[dict[str, Any]]) -> None:
    typer.echo(title)
    signs = {"added": "+", "removed": "-", "modified": "~"}
    for ch in changes:
        counts = "" if ch["binary"] else f" (+{ch['additions']} -{ch['deletions']})"
        typer.echo(f"  {signs[ch['status']]} {ch['path']}{counts}")


def register(app: typer.Typer) -> None:
    """Add ``update`` to the ``coffer skill`` group."""

    @app.command("update")
    def update(
        ctx: typer.Context,
        ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
        check_only: bool = typer.Option(
            False, "--check", help="Only check the source for newer commits"
        ),
        yes: bool = typer.Option(False, "--yes", "-y", help="Apply without asking"),
        take_theirs: bool = typer.Option(
            False, "--take-theirs", help="Apply over local edits, discarding them"
        ),
        keep_mine: bool = typer.Option(
            False, "--keep-mine", help="Keep local edits and stop offering this update"
        ),
        output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    ) -> None:
        """Check a Git-imported skill for updates, preview one and apply it."""
        verbose = verbose_of(ctx)
        if take_theirs and keep_mine:
            typer.echo("choose one of --take-theirs and --keep-mine", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        c, _info = _cli_client.client_or_exit()
        with c:
            uid = resolve_ref(c, "skill", ref, verbose=verbose)["uid"]
            if check_only:
                r = c.post(f"/skills/{uid}/source/check", timeout=_GIT_TIMEOUT_S)
                _cli_client.check(r, verbose=verbose)
                status = r.json()
                if output_json:
                    typer.echo(_json.dumps(status, indent=2))
                elif status["error"]:
                    typer.echo(f"source unreachable: {status['error']}")
                elif status["update_available"]:
                    typer.echo(
                        f"update available: {status['commits_ahead']} commit(s), "
                        f"{status['files_changed']} file(s), up to {status['latest_commit'][:7]}"
                    )
                else:
                    typer.echo("up to date")
                if status["error"]:
                    raise typer.Exit(int(ExitCode.GENERIC))
                return
            r = c.post(f"/skills/{uid}/source/preview", timeout=_GIT_TIMEOUT_S)
            _cli_client.check(r, verbose=verbose)
            p = r.json()
            stage = p["staging_id"]
            try:
                if p["up_to_date"]:
                    typer.echo("up to date")
                    raise typer.Exit(0)
                typer.echo(f"{p['from_commit'][:7]}..{p['to_commit'][:7]}")
                for commit in p["commits"]:
                    typer.echo(f"  {commit['id'][:7]} {commit['subject']}")
                _print_changes("changes:", p["changes"])
                if keep_mine:
                    k = c.post(f"/skills/{uid}/source/keep", json={"commit": p["to_commit"]})
                    _cli_client.check(k, verbose=verbose)
                    typer.echo(f"kept your version; {p['to_commit'][:7]} will not be offered again")
                    raise typer.Exit(0)
                if p["conflict"]:
                    _print_changes("your edits since the pin:", p["local_changes"])
                    if not take_theirs:
                        typer.echo(
                            "the skill was edited since its pinned commit; pass --take-theirs "
                            "to apply and discard the edits, or --keep-mine to keep them",
                            err=True,
                        )
                        raise typer.Exit(int(ExitCode.CONFLICT))
                if not yes and not typer.confirm("apply this update?", default=False):
                    typer.echo("nothing changed")
                    raise typer.Exit(0)
            except typer.Exit:
                _cancel(c, stage)
                raise
            a = c.post(
                f"/skills/{uid}/source/apply",
                json={"staging_id": stage, "discard_local_edits": take_theirs},
            )
            if a.is_error:
                _cancel(c, stage)
            _cli_client.check(a, verbose=verbose)
            typer.echo(f"updated: skill {a.json()['name']} to {p['to_commit'][:7]}")


__all__ = ["add_archive", "add_git", "looks_like_archive", "looks_like_git_url", "register"]
