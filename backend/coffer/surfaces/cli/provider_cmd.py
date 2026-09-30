"""`coffer provider …` — LLM connection commands (spec provider-switching).

``list``, ``show``, ``rm``, ``enable``, ``disable`` and ``scope`` are the
lifecycle verbs every kind's group shares (``_kind_verbs``). This kind keeps
its own ``add`` and ``edit``: creating a connection stores its secret through
the credential store, and editing it can rotate that secret or correct the
wire, both of which ``PATCH /providers/{uid}`` owns and the generic route does
not. ``switch`` and ``builtin`` are the connection-specific commands; the key an
agent used to fetch through ``key`` stays with the local model proxy, and the
agents run ``coffer proxy token`` instead.

Every command takes the connection's NAME and resolves it to the uid the
routes address (ADR resource-identity-is-an-immutable-uid).

Which connection the internal engine and speech-to-text run on is a setting,
``coffer config set engine.provider|transcribe.provider <name>``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._approvals import WAIT_OPTION, pending_for, settle
from coffer.surfaces.cli._kind_verbs import (
    Column,
    KindVerbs,
    check_title_arg,
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
        None, "--secret-ref", help="Reuse an existing secret ref instead of --secret"
    ),
    title: str | None = typer.Option(None, "--title", help="Display title (≤80 chars)"),
    description: str | None = typer.Option(None, "--description"),
    local: bool = typer.Option(
        False,
        "--local",
        help="A model runtime on this machine (Ollama, LM Studio, vLLM, llama-server): "
        "detect it, curate its tool-capable models, no key needed",
    ),
    wait: bool = WAIT_OPTION,
) -> None:
    """Create an LLM connection.

    With --local the base URL must be a loopback address; Coffer detects the
    runtime there read-only (nothing is pulled or loaded) and records the wires
    it serves and each model's served context window.

    For anthropic/openai/unknown supply exactly one of --secret /
    --secret-ref; an ollama connection needs neither. The new connection
    starts on the wire's own default reach; route it to specific agents (e.g. an
    openai gateway to Claude Code) with `coffer provider scope <name> --agents
    claude-code`. The model is chosen at the point of use, not on the
    connection.

    A --secret-ref key that already goes somewhere else waits for approval
    in the Coffer app before this connection may send it: the command says so
    and exits 9, or waits for the answer with --wait.

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

    check_title_arg(title)
    c, _info = _cli_client.client_or_exit()
    with c:
        if local:
            d = c.post("/providers/detect-local", json={"base_url": base_url})
            if d.status_code == 422:
                typer.echo(f"not a local address: {base_url}", err=True)
                raise typer.Exit(6)
            _cli_client.check(d, verbose=verbose)
            found = d.json()["found"]
            if not found:
                typer.echo(f"no local model runtime answers at {base_url}", err=True)
                raise typer.Exit(4)
            body["local_runtime"] = found[0]["runtime"]
            body["models"] = [
                {"id": m["id"], "context_window": m["context_window"]}
                for m in found[0]["models"]
                if m.get("tools") is not False
            ]
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
        # An existing key sent to this new base URL waits for the Coffer app
        # (spec secret "Hold a secret for a new destination until a person
        # approves it"): say so, and exit 9 unless --wait.
        settle(c, pending_for(c, data["uid"], verbose=verbose), wait=wait, verbose=verbose)


def detect_local(
    base_url: str | None = typer.Option(
        None, "--base-url", help="A loopback URL to probe; default: each runtime's default port"
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Find local model runtimes (read-only: nothing is pulled or loaded)."""
    import json as _json

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/providers/detect-local", json={"base_url": base_url})
        if r.status_code == 422:
            typer.echo(f"not a local address: {base_url}", err=True)
            raise typer.Exit(6)
        _cli_client.check(r, verbose=False)
    found = r.json()["found"]
    if json_out:
        typer.echo(_json.dumps(found, indent=2))
        return
    if not found:
        typer.echo("no local model runtime found")
        return
    for hit in found:
        rt = hit["runtime"]
        wires = ", ".join(rt["wires"]) or "none it can serve natively"
        typer.echo(f"{rt['runtime']} {rt.get('version') or ''} at {hit['base_url']} — {wires}")
        for m in hit["models"]:
            window = m["context_window"] or "window unknown"
            tools = {True: "tools", False: "no tools", None: "tools unknown"}[m["tools"]]
            typer.echo(f"  {m['id']}  ({window}, {tools})")


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
    wait: bool = WAIT_OPTION,
) -> None:
    """Rename a connection, or change its title, description, endpoint, wire or key.

    A rename changes the label and nothing else: the uid, the stored key and
    any projection into an agent stay where they are.

    A wire change is refused while the connection is switched on, because the
    wire decides whether a connection can cover any agent at all. Run
    `coffer provider builtin <agent_type>` first, edit, then
    `coffer provider switch <name>` again.

    A new --base-url for a connection whose key is already sent somewhere, or a
    new --secret for a key in use, waits for approval in the Coffer app: the
    change is saved, the command says what waits and exits 9, or waits for the
    answer with --wait.

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
        current = resolve_ref(c, "provider", ref, verbose=verbose)
        uid = current["uid"]
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
        if base_url is not None or secret is not None:
            # The key goes to the new base URL, and a new key replaces one in
            # use, only once a person approves it in the Coffer app (spec
            # secret "Hold a secret for a new destination until a person
            # approves it", "Hold a replaced value in use until a person
            # approves it"): say what waits, and exit 9 unless --wait.
            key_ref = _config(current, "credential_ref")
            refs = [str(key_ref)] if key_ref else []
            settle(c, pending_for(c, uid, verbose=verbose, refs=refs), wait=wait, verbose=verbose)


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
    agent_type: str = typer.Argument(..., help="Agent type: claude_code | codex"),
) -> None:
    """Switch's other half: put every agent of this type back on its OWN login.

    Removes Coffer's projection from the native config and clears the active
    connection covering it. Idempotent — a no-op when the agent already runs
    built-in.

    \f
    Takes the agent type the route is keyed by, the same vocabulary as
    ``coffer agent models``. A connection reaches agents through its scope, so
    no wire names an agent.
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/use-builtin/{agent_type}")
        if r.status_code in (400, 422):
            typer.echo(f"not an agent type: {agent_type!r}", err=True)
            raise typer.Exit(6)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    deprojected = ", ".join(data["deprojected"]) or "(no matching agent)"
    previous = data["previous"] or "(nothing was active)"
    typer.echo(f"{data['agent_type']} back on its built-in login, was {previous} → {deprojected}")


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
app.command("detect-local")(detect_local)
