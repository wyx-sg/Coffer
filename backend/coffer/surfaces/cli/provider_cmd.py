"""`coffer provider …` — LLM connection commands (spec provider-switching).

``list``, ``show``, ``rm``, ``enable``, ``disable`` and ``scope`` are the
lifecycle verbs every kind's group shares (``_kind_verbs``). This kind keeps
its own ``add`` and ``edit``: creating a connection stores its secret through
the credential store, and editing it can rotate that secret or correct the
wire, both of which ``PATCH /providers/{uid}`` owns and the generic route does
not. ``switch``, ``builtin`` and ``key`` are the connection-specific commands.

Every command takes the connection's NAME and resolves it to the uid the
routes address (ADR resource-identity-is-an-immutable-uid). ``key`` is the
exception: its caller is the ``apiKeyHelper`` line Coffer writes into another
tool's config file, so it takes the uid directly — a machine reading a value
Coffer put there, not a person typing.

Which connection the internal engine and speech-to-text run on is a setting,
``coffer config set engine.provider|transcribe.provider <name>``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import (
    Column,
    KindVerbs,
    register_kind_verbs,
    verbose_of,
)
from coffer.surfaces.cli._resolve import resolve_ref, resolve_uid

app = typer.Typer(help="Manage LLM connections and switch agents onto them")

_PROTOCOLS = "anthropic | openai | ollama | unknown"


def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Connection name"),
    protocol: str = typer.Option(..., "--protocol", help=f"Protocol: {_PROTOCOLS}"),
    base_url: str = typer.Option(..., "--base-url", help="Upstream endpoint base URL"),
    secret: str | None = typer.Option(None, "--secret", help="API key (stored encrypted)"),
    credential_ref: str | None = typer.Option(
        None, "--credential-ref", help="Reuse an existing credential ref instead of --secret"
    ),
    title: str | None = typer.Option(None, "--title", help="Display title (≤80 chars)"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Create an LLM connection.

    For anthropic/openai/unknown supply exactly one of --secret /
    --credential-ref; an ollama connection needs neither. The new connection
    starts on the wire's own default reach; route it to specific agents (e.g. an
    openai gateway to Claude Code) with `coffer provider scope <name> --agents
    claude-code`. The model is chosen at the point of use, not on the
    connection.

    \f
    Spec provider-switching "Take projected model keys from the agent's binding".
    """
    verbose = verbose_of(ctx)
    body: dict[str, object] = {"name": name, "protocol": protocol, "base_url": base_url}
    if secret is not None:
        body["secret_value"] = secret
    if credential_ref is not None:
        body["credential_ref"] = credential_ref
    if description is not None:
        body["description"] = description

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/providers", json=body)
        if r.status_code in (400, 422):
            typer.echo(f"invalid provider config: {r.text}", err=True)
            raise typer.Exit(6)
        if r.status_code == 409:
            typer.echo(f"provider {name!r} already exists", err=True)
            raise typer.Exit(5)
        _cli_client.check(r, verbose=verbose)
        data = r.json()
        if title:
            t = c.patch(f"/resources/{data['uid']}", json={"title": title})
            _cli_client.check(t, verbose=verbose)
    typer.echo(f"added provider {data['name']} ({data['protocol']})")


def _config(item: dict[str, Any], key: str) -> Any:
    return (item.get("config") or {}).get(key)


def edit(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
    new_name: str | None = typer.Option(None, "--name", help="New name"),
    title: str | None = typer.Option(
        None, "--title", help="Display title (≤80 chars); empty clears it"
    ),
    description: str | None = typer.Option(None, "--description"),
    protocol: str | None = typer.Option(
        None, "--protocol", help=f"Correct the wire format: {_PROTOCOLS}"
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    secret: str | None = typer.Option(None, "--secret", help="Rotate the stored API key"),
) -> None:
    """Rename a connection, or change its title, description, endpoint, wire or key.

    A rename changes the label and nothing else: the uid, the stored key and
    any projection into an agent stay where they are.

    A wire change is refused while the connection is switched on, because the
    wire decides which agents a connection can cover and which
    `coffer provider builtin <wire>` reverts. Run `builtin` first, edit, then
    `coffer provider switch <name>` again.

    \f
    Two routes, applied connection fields first: ``PATCH /providers/{uid}``
    owns the wire lock and the in-place key rotation, and the framework's
    ``PATCH /resources/{uid}`` owns the rename and the title (spec
    provider-switching "Rename a connection without moving anything else").
    A refused wire change therefore renames nothing.
    """
    verbose = verbose_of(ctx)
    patch: dict[str, object] = {}
    if protocol is not None:
        patch["protocol"] = protocol
    if base_url is not None:
        patch["base_url"] = base_url
    if secret is not None:
        patch["secret_value"] = secret
    if description is not None:
        patch["description"] = description
    relabel: dict[str, object] = {}
    if new_name is not None:
        relabel["name"] = new_name
    if title is not None:
        relabel["title"] = title
    if not patch and not relabel:
        typer.echo("nothing to update — specify at least one option", err=True)
        raise typer.Exit(6)

    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "provider", ref, verbose=verbose)["uid"]
        if patch:
            r = c.patch(f"/providers/{uid}", json=patch)
            if r.status_code == 409:
                # The daemon's message already names the connection and the
                # command that clears the way, so echo it rather than
                # paraphrasing it.
                envelope = r.json().get("error", {})
                typer.echo(envelope.get("message", f"provider {ref!r} is in use"), err=True)
                raise typer.Exit(5)
            if r.status_code in (400, 422):
                typer.echo(f"invalid update: {r.text}", err=True)
                raise typer.Exit(6)
            _cli_client.check(r, verbose=verbose)
        if relabel:
            r = c.patch(f"/resources/{uid}", json=relabel)
            _cli_client.check(r, verbose=verbose)
            ref = str(r.json()["name"])
    typer.echo(f"updated provider {ref}")


def switch(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Connection to activate"),
) -> None:
    """Switch the agents this connection reaches onto it and write their native config."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/{resolve_uid(c, 'provider', name, verbose=verbose)}/activate")
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    projected = ", ".join(data["projected"]) or "(no matching agent)"
    typer.echo(f"switched to {data['activated']} [{data['protocol']}] → {projected}")


def builtin(
    ctx: typer.Context,
    wire: str = typer.Argument(..., help="Wire format: anthropic | openai"),
) -> None:
    """Switch's other half: put this wire's agent(s) back on their OWN login.

    Removes Coffer's projection from the native config and clears the active
    connection. Idempotent — a no-op when the agent already runs built-in.

    \f
    Only the two wires that reach an agent are listed. `ollama` and `unknown`
    are accepted by the route (they are `Protocol` values) but map to no agent
    type, so the call reports nothing undone — naming them here would offer a
    command that cannot do anything.
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/use-builtin/{wire}")
        if r.status_code in (400, 422):
            typer.echo(f"not a wire format: {wire!r}", err=True)
            raise typer.Exit(6)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    deprojected = ", ".join(data["deprojected"]) or "(no matching agent)"
    previous = data["previous"] or "(nothing was active)"
    typer.echo(f"{data['protocol']} back on its built-in login, was {previous} → {deprojected}")


def key(
    connection_uid: str | None = typer.Option(
        None,
        "--connection-uid",
        help="Print this specific connection's key (the projected helper)",
    ),
    wire: str | None = typer.Option(
        None, "--wire", help="Back-compat: print the key active for a wire (anthropic | openai)"
    ),
) -> None:
    """Print a connection's API key for Claude Code's apiKeyHelper.

    Coffer writes this call into the agent's own config file when it switches
    the agent onto a connection; you rarely run it yourself. It takes the
    connection's uid, not its name, so renaming the connection keeps it working.

    --wire is the legacy form, which resolves whichever connection is active for
    that wire's agent instead of naming one.

    Exits 4 with nothing on stdout when the daemon resolves no key — for
    --connection-uid that includes a connection the user disabled or scoped to
    no agent, so the agent's helper fails instead of reading a stale key.

    \f
    The one command in this module that does NOT take a name. Its caller is the
    ``apiKeyHelper`` line Coffer writes into the agent's own config file, and
    that line has to keep resolving to the same connection after the user
    relabels it — so it cites the uid
    (ADR resource-identity-is-an-immutable-uid).
    """
    if connection_uid:
        path = f"/providers/{connection_uid}/key"
        missing = (
            f"no key for connection {connection_uid!r}: it is absent, disabled, "
            "scoped to no agent, or keyless"
        )
    elif wire:
        path, missing = f"/providers/active-key/{wire}", f"no active provider for wire {wire!r}"
    else:
        typer.echo("specify --connection-uid <uid> or --wire <wire>", err=True)
        raise typer.Exit(6)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(path)
        if r.status_code == 404:
            typer.echo(missing, err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    # Raw value only — apiKeyHelper consumes stdout as the token.
    typer.echo(r.json()["value"])


_PROVIDER = KindVerbs(
    kind="provider",
    noun="connection",
    verbs=frozenset({"list", "show", "rm", "enable", "disable", "scope"}),
    columns=(
        Column("Protocol", lambda it: str(_config(it, "protocol") or "")),
        Column("Base URL", lambda it: str(_config(it, "base_url") or "")),
        Column("Active", lambda it: "yes" if _config(it, "is_active") else ""),
        Column("Internal", lambda it: "yes" if _config(it, "internal_default") else ""),
    ),
    help={
        "list": "List every LLM connection.",
        "show": "Show one connection, by name or uid.",
        "rm": "Remove a connection (its stored key goes with it when nothing else cites it).",
    },
)


# Registered in one order so `--help` reads lifecycle first, then the
# connection-specific commands.
register_kind_verbs(app, dataclasses.replace(_PROVIDER, verbs=frozenset({"list", "show"})))
app.command("add")(add)
app.command("edit")(edit)
register_kind_verbs(
    app, dataclasses.replace(_PROVIDER, verbs=frozenset({"rm", "enable", "disable", "scope"}))
)
app.command("switch")(switch)
app.command("builtin")(builtin)
app.command("key")(key)
