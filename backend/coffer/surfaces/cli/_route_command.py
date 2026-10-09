"""Commands that are one REST route each, declared rather than hand-written.

Design align-cli-with-ui-and-add-tool-environments D1. A :class:`RouteCommand`
names a command path, the route it calls and the UI operation it stands for;
:func:`mount` turns it into a Typer command whose positional arguments are the
route's path parameters, whose options are its query parameters, and which
takes a body from ``--data``/``--set`` when the route has one. The request goes
through :func:`coffer.surfaces.cli._io.call`, so the daemon validates, audits
and applies it exactly as it does for the page; nothing is reimplemented here.

A path parameter listed in ``names`` takes a resource's NAME as well as its
uid, resolved once through ``GET /resources`` (``_resolve``).
"""

from __future__ import annotations

import inspect
import keyword
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import record

_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class Q:
    """One query parameter, as an option (``group_by`` is ``--group-by``)."""

    #: The route's own parameter name.
    name: str
    help: str = ""
    kind: type = str
    #: Repeatable (``--agent a --agent b``).
    multiple: bool = False
    #: A boolean switch (``--include-retired``).
    flag: bool = False


@dataclass(frozen=True)
class RouteCommand:
    command: str
    method: str
    route: str
    ui: str
    help: str
    query: tuple[Q, ...] = ()
    #: Whether the route takes a body (``--data``/``--set``).
    body: bool = False
    #: Path parameter -> resource kind, for ones that accept a name.
    names: Mapping[str, str] = field(default_factory=dict)
    #: Help per path parameter.
    args: Mapping[str, str] = field(default_factory=dict)
    #: For a human table: the key holding the rows, and the columns.
    rows: str | None = None
    columns: tuple[str, ...] = ()
    #: Report approvals the answer waits on with exit 9.
    pending: bool = False
    #: A test whose answer carries its outcome in this field: ``false`` exits 7
    #: (upstream test failed) after the whole answer is printed.
    outcome: str | None = None
    #: Query parameters always sent (``kind=mcp_server`` for a kind's list).
    fixed_query: Mapping[str, str] = field(default_factory=dict)
    #: Body fields always sent, under what ``--data``/``--set`` give.
    fixed_body: Mapping[str, Any] = field(default_factory=dict)


def _py(name: str) -> str:
    """A query parameter's name as a Python identifier (``from`` -> ``from_``)."""
    ident = name.replace("-", "_")
    return ident + "_" if keyword.iskeyword(ident) else ident


def _uid(kind: str, ref: str, *, as_json: bool) -> str:
    from coffer.surfaces.cli._resolve import resolve_ref

    with _io.client(as_json=as_json) as c:
        return str(resolve_ref(c, kind, ref, as_json=as_json)["uid"])


def _human(spec: RouteCommand) -> Callable[[Any], None] | None:
    if not spec.columns:
        return None

    def show(value: Any) -> None:
        rows: Any = value
        if isinstance(value, dict):
            rows = value.get(spec.rows) if spec.rows else None
            if rows is None:
                # The answer's one list, whatever the route calls it.
                rows = next((v for v in value.values() if isinstance(v, list)), value)
        if isinstance(rows, list):
            _io.table([r for r in rows if isinstance(r, dict)], list(spec.columns))
        else:
            _io.emit(value, as_json=False)

    return show


def build(spec: RouteCommand) -> Callable[..., None]:
    """The Typer callback for ``spec``, with a signature Typer can read."""
    path_params = _PARAM.findall(spec.route)
    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    for p in path_params:
        hint = spec.args.get(p) or (
            f"The {spec.names[p]}'s name or uid" if p in spec.names else p.replace("_", " ")
        )
        params.append(
            inspect.Parameter(
                p,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=typer.Argument(..., help=hint),
            )
        )
        annotations[p] = str
    for q in spec.query:
        py, flag = _py(q.name), "--" + q.name.replace("_", "-")
        if q.flag:
            default: Any = typer.Option(False, flag, help=q.help)
            annotations[py] = bool
        elif q.multiple:
            default = typer.Option(None, flag, help=q.help)
            annotations[py] = list[q.kind] | None  # type: ignore[name-defined]
        else:
            default = typer.Option(None, flag, help=q.help)
            annotations[py] = q.kind | None
        params.append(inspect.Parameter(py, inspect.Parameter.KEYWORD_ONLY, default=default))
    if spec.body:
        params.append(
            inspect.Parameter("data", inspect.Parameter.KEYWORD_ONLY, default=_io.data_option())
        )
        params.append(
            inspect.Parameter("sets", inspect.Parameter.KEYWORD_ONLY, default=_io.set_option())
        )
        annotations["data"] = str | None
        annotations["sets"] = list[str] | None
    params.append(
        inspect.Parameter("as_json", inspect.Parameter.KEYWORD_ONLY, default=_io.json_option())
    )
    annotations["as_json"] = bool

    def run(**kwargs: Any) -> None:
        as_json = bool(kwargs.pop("as_json", False))
        route = spec.route
        for p in path_params:
            value = str(kwargs.pop(p))
            if p in spec.names:
                value = _uid(spec.names[p], value, as_json=as_json)
            route = route.replace("{" + p + "}", value)
        body = None
        if spec.body:
            body = _io.body_from(
                kwargs.pop("data", None),
                kwargs.pop("sets", None),
                as_json=as_json,
                base=spec.fixed_body,
            )
        params_out: dict[str, Any] = {}
        for q in spec.query:
            given = kwargs.get(_py(q.name))
            params_out[q.name] = (given or None) if q.flag else given
        params_out.update(spec.fixed_query)
        answer = _io.call(spec.method, route, as_json=as_json, params=params_out, body=body)
        _io.emit(answer, as_json=as_json, human=_human(spec))
        if spec.pending:
            _io.report_pending(answer, as_json=as_json)
        if spec.outcome and isinstance(answer, dict) and answer.get(spec.outcome) is False:
            raise typer.Exit(int(ExitCode.UPSTREAM_TEST_FAILED))

    run.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    run.__annotations__ = annotations
    run.__doc__ = spec.help + f"\n\n\f\nRoute: {spec.method} /api/v1{spec.route}."
    run.__name__ = spec.command.replace(" ", "_").replace("-", "_")
    return run


#: Every declared command, for the test that runs each against its route.
MOUNTED: list[RouteCommand] = []


def mount(specs: list[RouteCommand]) -> None:
    """Add each command under its group and record its route."""
    for spec in specs:
        MOUNTED.append(spec)
        *parents, leaf = spec.command.split(" ")
        group(" ".join(parents)).command(leaf)(build(spec))
        record(spec.command, spec.method, spec.route, spec.ui)


__all__ = ["MOUNTED", "Q", "RouteCommand", "build", "mount"]
