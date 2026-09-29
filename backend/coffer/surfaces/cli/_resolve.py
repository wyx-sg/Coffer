"""Turning what a human typed into the uid the daemon addresses resources by.

A resource's identity is an opaque uid, and no human is going to type one
(ADR resource-identity-is-an-immutable-uid). The CLI therefore keeps taking
NAMES, and this module is the one place a name becomes a uid — so the
translation happens once, at the surface a person is standing at, instead of
being a thing every command re-invents or, worse, a second identity the daemon
has to accept.

The lookup is `GET /resources?kind=&name=`, the single route that is allowed to
find a resource by its label. That it costs a round trip is the honest price of
an opaque identity, and it is paid by the surface that created the need.
"""

from __future__ import annotations

from typing import Any

import httpx
import typer


def resolve_uid(client: httpx.Client, kind: str, name: str, *, verbose: bool = False) -> str:
    """The uid of the ``kind`` resource called ``name``.

    Exits 4 — the CLI's not-found code — with a message naming what was looked
    for, rather than letting a later request 404 on a uid the user never saw
    and cannot connect to what they typed.
    """
    return str(resolve(client, kind, name, verbose=verbose)["uid"])


def resolve(client: httpx.Client, kind: str, name: str, *, verbose: bool = False) -> dict[str, Any]:
    """The whole resource called ``name``, for a caller that wants more than the uid."""
    from coffer.surfaces.cli import _client as _cli_client

    r = client.get("/resources", params={"kind": kind, "name": name})
    _cli_client.check(r, verbose=verbose)
    matches = r.json()["resources"]
    if not matches:
        typer.echo(f"no {kind} named {name!r}", err=True)
        raise typer.Exit(4)
    # The (kind, name) uniqueness constraint makes a second match impossible;
    # asserting it here would add a branch no input can reach, so the first is
    # simply taken.
    return dict(matches[0])


def resolve_ref(
    client: httpx.Client, kind: str, ref: str, *, verbose: bool = False
) -> dict[str, Any]:
    """The ``kind`` resource that ``ref`` names — its name first, then its uid.

    The lifecycle verbs accept either (spec resource-framework "Address every
    resource by an immutable uid through one kind-agnostic surface"): a person
    types the name, a script that kept a uid from ``--json`` passes that. The
    name is tried first because it is what a person types; a uid of another
    kind is not an answer, so it reads as not found like any other miss.
    """
    from coffer.surfaces.cli import _client as _cli_client

    r = client.get("/resources", params={"kind": kind, "name": ref})
    _cli_client.check(r, verbose=verbose)
    matches = r.json()["resources"]
    if matches:
        return dict(matches[0])
    by_uid = client.get(f"/resources/{ref}")
    if by_uid.status_code == 200 and by_uid.json().get("kind") == kind:
        return dict(by_uid.json())
    if by_uid.status_code not in (200, 404, 422):
        _cli_client.check(by_uid, verbose=verbose)
    typer.echo(f"no {kind} named {ref!r}", err=True)
    raise typer.Exit(4)
