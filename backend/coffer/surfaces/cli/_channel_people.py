"""``coffer channel pair`` and ``unpair`` — who a channel answers (spec channels
"Gate inbound traffic on sender identity"). Split out of ``channel_cmd`` for its size budget."""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_uid

__all__ = ["pair", "unpair"]


def _person(client: Any, uid: str, ref: str, *, verbose: bool) -> dict[str, Any]:
    """The paired person ``ref`` names — by platform id or by display name."""
    r = client.get(f"/channels/{uid}/status")
    _cli_client.check(r, verbose=verbose)
    people = r.json().get("people") or []
    wanted = ref.strip().lower()
    for person in people:
        if wanted in (person["sender_id"].lower(), person["display_name"].lower()):
            return dict(person)
    typer.echo(f"no paired person {ref!r} on this channel", err=True)
    raise typer.Exit(int(ExitCode.NOT_FOUND))


def pair(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    replace: str | None = typer.Option(
        None,
        "--replace",
        metavar="PERSON",
        help="A paired person (id or name) whose place the new account takes",
    ),
) -> None:
    """Issue a pairing code; whoever sends it to the bot is added as a person.

    Everyone paired is answered with the same rights; strangers are not. With
    ``--replace`` the sender takes over that person's place instead of joining.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "channel", name, verbose=verbose)
        body_in: dict[str, str] = {}
        if replace:
            body_in["replaces"] = _person(c, uid, replace, verbose=verbose)["sender_id"]
        r = c.post(f"/channels/{uid}/pairing-code", json=body_in)
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    typer.echo(f"pairing code: {body['code']}")
    typer.echo(f"expires at:   {body['expires_at']}")
    if body.get("pair_url"):
        # "Pair by a one-tap start link": opening the link pairs in one tap; the
        # code still works typed.
        typer.echo(f"pair link:    {body['pair_url']}")
    typer.echo("Send this code to the bot from the account that should be able to use the channel.")


def unpair(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    person: str = typer.Argument(..., help="The paired person to remove (id or name)"),
) -> None:
    """Remove a paired person: their chats stop being answered; everyone else stays."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "channel", name, verbose=verbose)
        found = _person(c, uid, person, verbose=verbose)
        r = c.delete(f"/channels/{uid}/people/{found['sender_id']}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: {found['display_name']} from channel {name}")
