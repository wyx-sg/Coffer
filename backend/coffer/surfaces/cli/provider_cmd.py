"""`coffer provider …` — provider-profile CLI commands (spec provider-switching).

Every command here takes the connection's NAME and resolves it through
``_resolve`` to the uid the routes address
(ADR resource-identity-is-an-immutable-uid). ``key`` is the exception, and the
reason the rest of this change was possible: its caller is the ``apiKeyHelper``
line Coffer writes into another tool's config file, so it takes the uid
directly — a machine reading a value Coffer put there, not a person typing.

There is no ``rename`` here any more. Renaming is a field on every resource now
(``coffer resource rename provider <name> <new>``); this kind only ever had a
verb of its own because its name was written out into that same config file, and
it no longer is.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Manage provider profiles and switch the active provider")
_console = Console()


@app.command("add")
def add(
    name: str = typer.Argument(..., help="Profile name"),
    protocol: str = typer.Option(
        ..., "--protocol", help="Protocol: anthropic | openai | ollama | unknown"
    ),
    base_url: str = typer.Option(..., "--base-url", help="Upstream endpoint base URL"),
    secret: str | None = typer.Option(None, "--secret", help="API key (stored encrypted)"),
    credential_ref: str | None = typer.Option(
        None, "--credential-ref", help="Reuse an existing credential ref instead of --secret"
    ),
) -> None:
    """Create an LLM connection. For anthropic/openai/unknown supply exactly one
    of --secret / --credential-ref; an ollama connection needs neither. The new
    connection starts on the wire's own default scope; route it to specific
    agents (e.g. an openai gateway to claude_code) with
    `coffer scope set provider <name> --agents claude-code`. The model is chosen
    at the point of use (`coffer agent edit --model`), not on the connection.

    \f
    Spec provider-switching "Take projected model keys from the agent's binding"."""
    body: dict[str, object] = {
        "name": name,
        "protocol": protocol,
        "base_url": base_url,
    }
    if secret is not None:
        body["secret_value"] = secret
    if credential_ref is not None:
        body["credential_ref"] = credential_ref

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/providers", json=body)
        if r.status_code in (400, 422):
            typer.echo(f"invalid provider config: {r.text}", err=True)
            raise typer.Exit(6)
        if r.status_code == 409:
            typer.echo(f"provider {name!r} already exists", err=True)
            raise typer.Exit(5)
        r.raise_for_status()
    data = r.json()
    typer.echo(f"added provider {data['name']} ({data['protocol']})")


@app.command("list")
def list_providers(output_json: bool = typer.Option(False, "--json")) -> None:
    """List all provider profiles."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/providers")
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Providers")
    for col in ("name", "protocol", "base_url", "active", "internal"):
        table.add_column(col)
    for p in data["providers"]:
        table.add_row(
            p["name"],
            p["protocol"],
            p["base_url"],
            "yes" if p["is_active"] else "",
            "yes" if p.get("internal_default") else "",
        )
    _console.print(table)


@app.command("show")
def show(name: str = typer.Argument(..., help="Profile name")) -> None:
    """Show one provider profile."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/providers/{resolve_uid(c, 'provider', name)}")
        r.raise_for_status()
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("edit")
def edit(
    name: str = typer.Argument(..., help="Profile name"),
    protocol: str | None = typer.Option(
        None,
        "--protocol",
        help="Correct the wire format: anthropic | openai | ollama | unknown",
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    secret: str | None = typer.Option(None, "--secret", help="Rotate the stored API key"),
) -> None:
    """Edit a connection's endpoint, wire format or key.

    `credential_ref` is the immutable one: it is the vault address the
    connection owns. The WIRE is not — the probe that guessed it can be wrong,
    and correcting it in place is what saves re-entering the key.

    A wire change is refused while the connection is switched on, because the
    wire decides which agents a connection can cover and which
    `coffer provider use-builtin <wire>` reverts. Run `use-builtin` first, edit,
    then `coffer provider switch <name>` again.
    """
    patch: dict[str, object] = {}
    if protocol is not None:
        patch["protocol"] = protocol
    if base_url is not None:
        patch["base_url"] = base_url
    if secret is not None:
        patch["secret_value"] = secret
    if not patch:
        typer.echo("nothing to update — specify at least one option", err=True)
        raise typer.Exit(6)

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/providers/{resolve_uid(c, 'provider', name)}", json=patch)
        if r.status_code == 409:
            # The daemon's message already names the connection and the command
            # that clears the way, so echo it rather than paraphrasing it.
            envelope = r.json().get("error", {})
            typer.echo(envelope.get("message", f"provider {name!r} is in use"), err=True)
            raise typer.Exit(5)
        if r.status_code in (400, 422):
            typer.echo(f"invalid update: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    typer.echo(f"updated provider {name}")


@app.command("rm")
def rm(name: str = typer.Argument(..., help="Profile name")) -> None:
    """Remove a provider profile."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/providers/{resolve_uid(c, 'provider', name)}")
        r.raise_for_status()
    typer.echo(f"removed provider {name}")


@app.command("switch")
def switch(name: str = typer.Argument(..., help="Profile to activate")) -> None:
    """Switch: make this profile active for its wire and write native config."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/{resolve_uid(c, 'provider', name)}/activate")
        r.raise_for_status()
    data = r.json()
    projected = ", ".join(data["projected"]) or "(no matching agent)"
    typer.echo(f"switched to {data['activated']} [{data['protocol']}] → {projected}")


@app.command("use-builtin")
def use_builtin(
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
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/use-builtin/{wire}")
        if r.status_code in (400, 422):
            typer.echo(f"not a wire format: {wire!r}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    data = r.json()
    deprojected = ", ".join(data["deprojected"]) or "(no matching agent)"
    previous = data["previous"] or "(nothing was active)"
    typer.echo(f"{data['protocol']} back on its built-in login, was {previous} → {deprojected}")


@app.command("internal-default")
def internal_default(name: str = typer.Argument(..., help="Connection to use internally")) -> None:
    """Make this connection the one Coffer's own model runs on (at most one)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/{resolve_uid(c, 'provider', name)}/internal-default")
        r.raise_for_status()
    data = r.json()
    typer.echo(f"internal engine now uses {data['name']} [{data['protocol']}]")


@app.command("transcribe-default")
def transcribe_default(
    name: str = typer.Argument(..., help="Connection Coffer transcribes speech on"),
) -> None:
    """Make this connection the one Coffer transcribes speech on (≤1 globally).

    A separate flag from internal-default, not a fallback to it: a gateway that
    serves chat completions commonly serves no transcription endpoint at all.
    Pair it with `coffer engine transcribe-model set <model>` — with either
    half missing, Coffer transcribes nothing and the agent gets the audio file.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/{resolve_uid(c, 'provider', name)}/transcribe-default")
        r.raise_for_status()
    data = r.json()
    typer.echo(f"speech is now transcribed on {data['name']} [{data['protocol']}]")


@app.command("key")
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
    """Print a provider's API key for Claude Code's apiKeyHelper.

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
    (ADR resource-identity-is-an-immutable-uid). Taking a name here as well
    would put the rename back into the projected file, which is the exact cost
    this change removed.
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
