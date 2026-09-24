"""``coffer skill files|cat|write`` — a skill's master folder from a terminal.

The CLI half of the file viewer and editor the web Files tab already drives
(spec skill-manager "Show a skill's master folder read-only", "Save an existing
skill file conditionally"): the same three routes under
``/api/v1/skills/{uid}/files``, so REST, CLI and web share one endpoint and one
containment guard.

Its own module for the backend 400-line file cap; ``attach`` registers the
commands on ``skill_cmd``'s typer so the tree stays ``coffer skill ...``. Like
its siblings it takes the skill's NAME and resolves it once to the uid the
routes address (ADR resource-identity-is-an-immutable-uid).
"""

from __future__ import annotations

import json as _json
import pathlib
import sys
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _lines(node: dict[str, Any]) -> list[str]:
    """One line per entry below the root, directories first as the route sorts
    them: the folder-relative path (a trailing ``/`` on a directory) and a
    file's size."""
    out: list[str] = []
    for child in node["children"]:
        if child["type"] == "dir":
            out.append(f"{child['path']}/" + ("  (truncated)" if child["truncated"] else ""))
            out.extend(_lines(child))
        else:
            out.append(f"{child['path']}  {child['size']} B")
    return out


def files(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List a skill's master folder as a file tree."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "skill", name, verbose=verbose)
        r = c.get(f"/skills/{uid}/files")
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(data["root"]["abs_path"])
    for line in _lines(data["root"]):
        typer.echo(f"  {line}")


def cat(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name"),
    path: str = typer.Argument(..., help="Path inside the skill folder, e.g. SKILL.md"),
    output_json: bool = typer.Option(
        False, "--json", help="The whole read: content, fingerprint, size, binary, truncated"
    ),
) -> None:
    """Print one file of a skill's master folder."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "skill", name, verbose=verbose)
        r = c.get(f"/skills/{uid}/files/content", params={"path": path})
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if data["binary"]:
        typer.echo(f"{path}: binary file ({data['size']} bytes), not printed", err=True)
        return
    typer.echo(data["content"], nl=False)
    if data["truncated"]:
        typer.echo(f"\n[truncated: the file is {data['size']} bytes]", err=True)


def write(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name"),
    path: str = typer.Argument(..., help="Existing text file inside the skill folder"),
    from_file: str | None = typer.Option(
        None, "--from-file", help="Read the new content from PATH instead of stdin"
    ),
    fingerprint: str | None = typer.Option(
        None,
        "--fingerprint",
        help="The fingerprint of the read your edit started from (`skill cat --json`); "
        "default: a fresh read taken just before the write",
    ),
) -> None:
    """Overwrite an existing text file in a skill's master folder.

    The write is conditional: it carries a fingerprint, and a file changed on
    disk since then is refused (exit 5) and left as it is. Coffer's own builtin
    skill is refused (exit 5) because it is rewritten from the build."""
    verbose = _verbose(ctx)
    if from_file is not None:
        try:
            content = pathlib.Path(from_file).read_text(encoding="utf-8")
        except OSError as e:
            typer.echo(f"cannot read {from_file}: {e}", err=True)
            raise typer.Exit(1) from e
    else:
        content = sys.stdin.read()
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "skill", name, verbose=verbose)
        if fingerprint is None:
            read = c.get(f"/skills/{uid}/files/content", params={"path": path})
            _cli_client.check(read, verbose=verbose)
            fingerprint = read.json()["fingerprint"]
        w = c.put(
            f"/skills/{uid}/files/content",
            json={"path": path, "content": content, "expected_fingerprint": fingerprint},
        )
        _cli_client.check(w, verbose=verbose)
    typer.echo(f"saved: {path} (fingerprint {w.json()['fingerprint'][:12]})")


def attach(app: typer.Typer) -> None:
    """Register the master-folder commands on ``skill_cmd``'s typer."""
    app.command("files")(files)
    app.command("cat")(cat)
    app.command("write")(write)
