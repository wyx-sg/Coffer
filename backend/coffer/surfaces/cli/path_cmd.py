"""``coffer path`` — where the plain files behind Coffer's state live.

Knowledge documents, memory notes, skill master folders, agents' own config,
native memory and transcripts, and the daemon log are plain files that a person
or an agent reads and edits with their own tools. This command names them as
absolute paths — one per line, or one JSON object keyed by what each path is —
and creates and changes nothing (spec resource-framework "Locate file-backed
state with coffer path").

Resource paths come from reads the daemon already serves: the skill's
``master_path``, a partition's file tree, an agent's config-file listing,
native-memory scan and transcript listing. A collection's directory is its name
under the knowledge root, found through the collection listing. The roots
themselves, and the log directory, resolve through the same functions and the
same ``COFFER_*`` overrides the daemon uses, so printing them needs no daemon.
"""

from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Any

import httpx
import typer

from coffer.infrastructure.knowledge.paths import knowledge_root
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.memory.paths import memory_root
from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(
    help="Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)",
    invoke_without_command=True,
)

_JSON = typer.Option(False, "--json", help="JSON object keyed by what each path is")


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _emit(paths: dict[str, Any], output_json: bool, *, lines: list[str] | None = None) -> None:
    if output_json:
        typer.echo(_json.dumps(paths, indent=2))
        return
    for line in lines if lines is not None else [str(v) for v in paths.values()]:
        typer.echo(line)


def _abs(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def _vault() -> str:
    return _abs(Path(os.environ.get("HOME", "~")).expanduser() / ".coffer")


def _logs() -> dict[str, str]:
    directory = _abs(log_dir())
    return {"logs": directory, "daemon_log": str(Path(directory) / "daemon.log")}


def _read(c: httpx.Client, path: str, *, verbose: bool, **params: Any) -> Any:
    """GET ``path``; an error answer is rendered and exits."""
    r = c.get(path, params=params or None)
    _cli_client.check(r, verbose=verbose)
    return r.json()


def _not_found(what: str, name: str) -> typer.Exit:
    typer.echo(f"no {what} named {name!r}", err=True)
    return typer.Exit(4)


@app.callback()
def roots(ctx: typer.Context, output_json: bool = _JSON) -> None:
    """With no target, print every root: the vault, knowledge, memory, skills and logs."""
    if ctx.invoked_subcommand is not None:
        return
    paths = {
        "vault": _vault(),
        "knowledge": _abs(knowledge_root()),
        "memory": _abs(memory_root()),
        "skills": _abs(default_master_root()),
    }
    paths.update(_logs())
    _emit(paths, output_json, lines=[f"{k}: {v}" for k, v in paths.items()])


@app.command("knowledge")
def knowledge(
    ctx: typer.Context,
    collection: str | None = typer.Argument(None, help="A collection; omit for the knowledge root"),
    output_json: bool = _JSON,
) -> None:
    """The knowledge root, or one collection's directory of Markdown documents."""
    c, _info = _cli_client.client_or_exit()
    with c:
        listed = _read(c, "/knowledge/collections", verbose=_verbose(ctx))
    root = _abs(knowledge_root())
    if collection is None:
        _emit({"knowledge": root}, output_json)
        return
    match = [x for x in listed["collections"] if collection in (x["name"], x["uid"])]
    if not match:
        raise _not_found("knowledge collection", collection)
    directory = str(Path(root) / match[0]["name"])
    _emit({"knowledge": root, "collection": directory}, output_json, lines=[directory])


@app.command("memory")
def memory(
    ctx: typer.Context,
    partition: str | None = typer.Argument(None, help="A partition; omit for the memory root"),
    output_json: bool = _JSON,
) -> None:
    """The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        listed = _read(c, "/memory/partitions", verbose=verbose)
        if partition is None:
            _emit({"memory": _abs(memory_root())}, output_json)
            return
        match = [p for p in listed["partitions"] if partition in (p["name"], p["uid"])]
        if not match:
            raise _not_found("memory partition", partition)
        tree = _read(c, f"/memory/partitions/{match[0]['uid']}/files", verbose=verbose)
    node = tree["root"]
    _emit(
        {"memory": node["folder_abs_path"], "partition": node["abs_path"]},
        output_json,
        lines=[node["abs_path"]],
    )


@app.command("skill")
def skill(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name"),
    output_json: bool = _JSON,
) -> None:
    """A skill's master folder, which a person edits in place."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        body = _read(
            c,
            f"/skills/{resolve_uid(c, 'skill', name, verbose=verbose)}",
            feature=None,
            verbose=verbose,
        )
    _emit({"skill": _abs(body["master_path"])}, output_json)


_AGENT_FILES = ("config", "memory", "transcripts")


@app.command("agent")
def agent(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    what: str = typer.Argument(..., metavar="config|memory|transcripts"),
    output_json: bool = _JSON,
) -> None:
    """An agent's own files: its config files, native memory stores, or transcript folders."""
    if what not in _AGENT_FILES:
        typer.echo(f"pick one of: {', '.join(_AGENT_FILES)}", err=True)
        raise typer.Exit(2)
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        if what == "config":
            items = _read(c, f"/agents/{uid}/config-files", feature=None, verbose=verbose)["items"]
            paths = [i["path"] for i in items if i["exists"]]
        elif what == "memory":
            items = _read(c, f"/agents/{uid}/native-memory", feature=None, verbose=verbose)["items"]
            paths = [i["memory_dir"] for i in items]
        else:
            paths = _transcript_dirs(c, uid, verbose=verbose)
    found = [_abs(p) for p in paths]
    _emit({what: found}, output_json, lines=found)


def _transcript_dirs(c: httpx.Client, uid: str, *, verbose: bool) -> list[str]:
    """Every folder holding one of the agent's transcript files, in listing order."""
    dirs: dict[str, None] = {}
    params: dict[str, Any] = {"limit": 500}
    while True:
        page = _read(c, f"/agents/{uid}/transcripts", feature=None, verbose=verbose, **params)
        for s in page["sessions"]:
            dirs.setdefault(str(Path(s["source_path"]).parent), None)
        if not page.get("next_cursor"):
            return list(dirs)
        params["cursor"] = page["next_cursor"]


@app.command("logs")
def logs(output_json: bool = _JSON) -> None:
    """The log directory and the daemon.log in it (COFFER_LOG_DIR moves both)."""
    _emit(_logs(), output_json)


@app.command("vault")
def vault(output_json: bool = _JSON) -> None:
    """The directory that holds this machine's vault."""
    _emit({"vault": _vault()}, output_json)
