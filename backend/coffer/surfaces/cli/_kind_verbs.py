"""The lifecycle verbs every kind's group shares, generated from one descriptor.

``list``, ``show``, ``edit``, ``rm``, ``enable``, ``disable`` and ``scope``
are the same operation on every kind, served by the same
kind-agnostic routes (``/resources*``), so they are written once here and
registered onto each kind's Typer group (spec resource-framework "Address every
resource by an immutable uid through one kind-agnostic surface"). A verb the
kind cannot support is simply not registered: a missing command is a clearer
answer than one that refuses when run.

A per-kind module calls :func:`register_kind_verbs` with a :class:`KindVerbs`
descriptor. It may add its own commands beside them. Creation is not one of
these verbs: a kind that can be created from its group registers an ``add`` of
its own, because what creating one takes differs by kind (spec
resource-framework "Keep creation a per-kind seam"). Kind-specific ``edit``
flags come in through :class:`EditFlags` rather than a second ``edit``
spelling.
"""

from __future__ import annotations

import inspect
import json as _json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.domain.resource import TITLE_MAX_LEN
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_ref, resolve_uid

#: Every lifecycle verb, in the order a group's ``--help`` lists them.
ALL_VERBS: tuple[str, ...] = ("list", "show", "edit", "rm", "enable", "disable", "scope")
#: What a kind gets unless it says otherwise: reach is opt-in, because it needs
#: the kind to support it.
DEFAULT_VERBS: frozenset[str] = frozenset({"list", "show", "edit", "rm", "enable", "disable"})

_console = Console()


@dataclass(frozen=True)
class Column:
    """One kind-specific column of ``list``: a header and how to fill it from a
    resource document (as ``GET /resources`` returns it)."""

    header: str
    cell: Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class EditFlags:
    """A kind's own ``edit`` flags.

    ``params`` are ``inspect.Parameter`` objects whose default is a
    ``typer.Option(...)``, spliced into the generated ``edit`` signature.
    ``to_config(resource, values)`` receives the current resource document and
    the flags' values by parameter name, and returns the WHOLE new config, or
    ``None`` when those flags change nothing.
    """

    params: Sequence[inspect.Parameter]
    to_config: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class KindVerbs:
    """What the factory needs to know about one kind.

    ``kind`` is the REST kind (``mcp_server``); ``noun`` is what a message calls
    one (``MCP server``). ``name_fixed`` keeps ``edit --name`` but says in its
    help that the daemon refuses it: the refusal (``NAME_IMMUTABLE``) is what
    tells the user to delete and register again, and what that resets (spec
    resource-framework "Treat a resource's name as a mutable label"), which a
    missing option could not.

    ``edit_description`` is ``False`` for a kind whose description is not a
    field of the resource — a knowledge collection's comes from its README
    (spec knowledge "Read a collection's description from its README") — so
    ``edit`` offers no ``--description`` that would write one nobody reads.
    """

    kind: str
    noun: str
    verbs: frozenset[str] = DEFAULT_VERBS
    name_fixed: bool = False
    edit_description: bool = True
    columns: tuple[Column, ...] = ()
    edit_flags: EditFlags | None = None
    help: dict[str, str] = field(default_factory=dict)


def label(resource: dict[str, Any]) -> str:
    """The title where one is set, the name where it is not (spec
    resource-framework "Carry an optional editable title on every resource").
    A daemon that predates ``title`` sends none, which reads as unset."""
    return str(resource.get("title") or resource["name"])


def check_title_arg(title: str | None) -> None:
    """Refuse an over-long ``--title`` before anything is registered.

    Every ``add`` registers first and sets the title in a second call; checking
    here keeps a refused title from leaving a registered resource behind.
    """
    if title is not None and len(title.strip()) > TITLE_MAX_LEN:
        typer.echo(f"--title is at most {TITLE_MAX_LEN} characters", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))


def verbose_of(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


# --- reach (agent names on the surface, uids in the stored value) -----------


def _agent_uids(c: httpx.Client, names: list[str], *, verbose: bool) -> list[str]:
    return [resolve_uid(c, "agent", name, verbose=verbose) for name in names]


def agent_names(
    c: httpx.Client, scope: dict[str, Any] | None, *, verbose: bool
) -> dict[str, Any] | None:
    """The stored scope with its agent uids rendered back as names; a uid with
    no agent behind it is shown verbatim, since it is a real entry."""
    if scope is None or scope.get("agents") is None:
        return scope
    r = c.get("/resources", params={"kind": "agent"})
    _cli_client.check(r, verbose=verbose)
    names = {a["uid"]: a["name"] for a in r.json()["resources"]}
    return {**scope, "agents": [names.get(uid, uid) for uid in scope["agents"]]}


def reach_line(scope: dict[str, Any] | None) -> str:
    if scope is None or scope.get("agents") is None:
        return "every agent"
    if not scope["agents"]:
        return "no agent (dormant)"
    return ", ".join(scope["agents"])


# --- the verbs ----------------------------------------------------------------


def _list(spec: KindVerbs) -> Callable[..., None]:
    def list_cmd(
        ctx: typer.Context,
        output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    ) -> None:
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.get("/resources", params={"kind": spec.kind})
            _cli_client.check(r, verbose=verbose_of(ctx))
        data = r.json()["resources"]
        if output_json:
            typer.echo(_json.dumps({"resources": data}, indent=2))
            return
        table = Table(title=spec.noun)
        table.add_column("Name")
        table.add_column("Enabled")
        for col in spec.columns:
            table.add_column(col.header)
        for item in data:
            table.add_row(
                label(item),
                "yes" if item["enabled"] else "no",
                *(col.cell(item) for col in spec.columns),
            )
        _console.print(table)

    list_cmd.__doc__ = spec.help.get("list", f"List every {spec.noun}.")
    return list_cmd


def _show(spec: KindVerbs) -> Callable[..., None]:
    def show(
        ctx: typer.Context,
        ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
        output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    ) -> None:
        verbose = verbose_of(ctx)
        c, _info = _cli_client.client_or_exit()
        with c:
            uid = resolve_ref(c, spec.kind, ref, verbose=verbose)["uid"]
            r = c.get(f"/resources/{uid}")
            _cli_client.check(r, verbose=verbose)
        data = r.json()
        if output_json:
            typer.echo(_json.dumps(data, indent=2))
            return
        typer.echo(label(data))
        typer.echo(f"name:         {data['name']}")
        if data.get("title"):
            typer.echo(f"title:        {data['title']}")
        typer.echo(f"uid:          {data['uid']}")
        typer.echo(f"enabled:      {'yes' if data['enabled'] else 'no'}")
        if data.get("description"):
            typer.echo(f"description:  {data['description']}")
        typer.echo(f"config:       {_json.dumps(data['config'])}")

    show.__doc__ = spec.help.get("show", f"Show one {spec.noun}, by name or uid.")
    return show


def _edit(spec: KindVerbs) -> Callable[..., None]:
    extra = list(spec.edit_flags.params) if spec.edit_flags else []
    extra_names = [p.name for p in extra]

    def edit(ctx: typer.Context, **kwargs: Any) -> None:
        verbose = verbose_of(ctx)
        ref = kwargs.pop("ref")
        body: dict[str, Any] = {}
        if kwargs.get("new_name") is not None:
            body["name"] = kwargs["new_name"]
        for key in ("title", "description"):
            if kwargs.get(key) is not None:
                body[key] = kwargs[key]
        values = {n: kwargs.get(n) for n in extra_names}
        c, _info = _cli_client.client_or_exit()
        with c:
            current = resolve_ref(c, spec.kind, ref, verbose=verbose)
            if spec.edit_flags is not None:
                new_config = spec.edit_flags.to_config(current, values)
                if new_config is not None:
                    body["config"] = new_config
            if not body:
                typer.echo("nothing to change: name at least one option", err=True)
                raise typer.Exit(2)
            r = c.patch(f"/resources/{current['uid']}", json=body)
            _cli_client.check(r, verbose=verbose)
        typer.echo(f"updated: {spec.noun} {label(r.json())}")

    base = [
        inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=typer.Context),
        _param("ref", str, typer.Argument(..., metavar="NAME", help="Name or uid")),
    ]
    name_help = (
        "Refused: this kind's name is fixed once registered (use --title)"
        if spec.name_fixed
        else "New name"
    )
    base.append(_param("new_name", str | None, typer.Option(None, "--name", help=name_help)))
    base += [
        _param(
            "title",
            str | None,
            typer.Option(None, "--title", help="Display title (≤80 chars); empty clears it"),
        ),
    ]
    if spec.edit_description:
        base.append(_param("description", str | None, typer.Option(None, "--description")))
    edit.__signature__ = inspect.Signature([*base, *extra])  # type: ignore[attr-defined]
    edit.__doc__ = spec.help.get("edit", f"Change a {spec.noun}'s title, description or settings.")
    return edit


def _param(name: str, annotation: Any, default: Any) -> inspect.Parameter:
    return inspect.Parameter(
        name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=annotation
    )


def _rm(spec: KindVerbs) -> Callable[..., None]:
    def rm(
        ctx: typer.Context,
        ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
        yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask"),
    ) -> None:
        verbose = verbose_of(ctx)
        if not yes and not typer.confirm(f"Really remove {spec.noun} {ref}?"):
            raise typer.Exit(1)
        c, _info = _cli_client.client_or_exit()
        with c:
            uid = resolve_ref(c, spec.kind, ref, verbose=verbose)["uid"]
            r = c.delete(f"/resources/{uid}")
            _cli_client.check(r, verbose=verbose)
        typer.echo(f"removed: {spec.noun} {ref}")

    rm.__doc__ = spec.help.get("rm", f"Remove a {spec.noun}.")
    return rm


def _toggle(spec: KindVerbs, action: str) -> Callable[..., None]:
    def toggle(
        ctx: typer.Context,
        ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
    ) -> None:
        verbose = verbose_of(ctx)
        c, _info = _cli_client.client_or_exit()
        with c:
            uid = resolve_ref(c, spec.kind, ref, verbose=verbose)["uid"]
            r = c.post(f"/resources/{uid}/{action}")
            _cli_client.check(r, verbose=verbose)
        typer.echo(f"{action}d: {spec.noun} {label(r.json())}")

    toggle.__doc__ = spec.help.get(action, f"{action.capitalize()} a {spec.noun}.")
    return toggle


def _scope(spec: KindVerbs) -> Callable[..., None]:
    def scope(
        ctx: typer.Context,
        ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
        agents: str | None = typer.Option(None, "--agents", help="Only these agents (a,b)"),
        all_: bool = typer.Option(False, "--all", help="Every agent"),
        none: bool = typer.Option(False, "--none", help="No agent (dormant)"),
        output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    ) -> None:
        verbose = verbose_of(ctx)
        if sum([agents is not None, all_, none]) > 1:
            typer.echo("pick at most one of --agents / --all / --none", err=True)
            raise typer.Exit(2)
        named = None if agents is None else [n.strip() for n in agents.split(",") if n.strip()]
        if named == []:
            typer.echo("--agents needs at least one name", err=True)
            raise typer.Exit(2)
        c, _info = _cli_client.client_or_exit()
        with c:
            uid = resolve_ref(c, spec.kind, ref, verbose=verbose)["uid"]
            if named is None and not all_ and not none:
                r = c.get(f"/resources/{uid}/scope")
            else:
                stored = (
                    None
                    if all_
                    else {"agents": [] if none else _agent_uids(c, named or [], verbose=verbose)}
                )
                r = c.put(f"/resources/{uid}/scope", json={"scope": stored})
            _cli_client.check(r, verbose=verbose)
            shown = agent_names(c, r.json()["scope"], verbose=verbose)
        if output_json:
            typer.echo(_json.dumps({"scope": shown}, indent=2))
            return
        typer.echo(f"reach: {reach_line(shown)}")

    scope.__doc__ = spec.help.get(
        "scope", f"Show or set which agents a {spec.noun} reaches (this machine only)."
    )
    return scope


def register_kind_verbs(app: typer.Typer, spec: KindVerbs) -> None:
    """Register ``spec``'s lifecycle verbs on ``app``, in :data:`ALL_VERBS` order."""
    unknown = spec.verbs - set(ALL_VERBS)
    if unknown:
        raise ValueError(f"unknown lifecycle verbs for {spec.kind}: {sorted(unknown)}")
    builders: dict[str, Callable[[], Callable[..., None]]] = {
        "list": lambda: _list(spec),
        "show": lambda: _show(spec),
        "edit": lambda: _edit(spec),
        "rm": lambda: _rm(spec),
        "enable": lambda: _toggle(spec, "enable"),
        "disable": lambda: _toggle(spec, "disable"),
        "scope": lambda: _scope(spec),
    }
    for verb in ALL_VERBS:
        if verb in spec.verbs:
            app.command(verb)(builders[verb]())
