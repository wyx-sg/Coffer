"""MCP-specific Kind wiring used by the composition root."""

from __future__ import annotations

import contextlib
from typing import Any

from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, Resource

# Keys inside ``transport`` whose values may carry auth material (custom
# headers, raw environment overlays). secret_refs (keychain ref strings
# only) survive audit; the raw maps are stripped.
_AUDIT_STRIP_TRANSPORT_KEYS: frozenset[str] = frozenset({"env", "headers"})


def _mcp_audit_redactor(config: dict[str, Any]) -> dict[str, Any]:
    """Strip auth-bearing maps from an mcp_server config before audit.

    Clients can paste custom auth headers / env vars into MCP server config
    (e.g. an Authorization header on an HTTP transport). Those are materialised
    at spawn time from the keychain, but a careless user might paste the raw
    secret in instead — and we don't want it landing verbatim in
    audit_log.details_json. Stripping the structural maps keeps audit useful
    (secret_refs survive; users still see *what* changed) without ever
    persisting the secret material itself.
    """
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return config
    sanitised = {k: v for k, v in transport.items() if k not in _AUDIT_STRIP_TRANSPORT_KEYS}
    return {**config, "transport": sanitised}


def _mcp_secret_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Pull ``transport.secret_refs`` out of a validated mcp_server config."""
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return {}
    refs = transport.get("secret_refs")
    if not isinstance(refs, dict):
        return {}
    return {str(k): str(v) for k, v in refs.items()}


def _validate_mcp_name(name: str) -> None:
    """Reject mcp_server names that would break tool/prompt namespacing.

    Capabilities are exposed downstream as ``<server>__<tool>`` and
    parsed back by splitting on the first ``__``. A server name containing
    ``__`` makes that parse ambiguous (it would route to the wrong server, so
    the tool lists but can never be invoked). Reserve the separator.
    """
    if "__" in name:
        raise ValueError(
            f"mcp_server name {name!r} may not contain '__' "
            "(reserved as the tool/prompt namespace separator)"
        )


#: The longest name a NEW server may take (spec mcp-gateway "Manage MCP servers
#: as resources"). ``mcp__coffer__`` (13) + the name + ``__`` (2) is the part of
#: a client's 64-character tool-name budget the name spends, and 24 leaves 25
#: characters for the upstream tool's own name.
MCP_SERVER_NAME_MAX_LEN = 24


def _cap_new_mcp_name(name: str) -> None:
    """Refuse a new server name longer than :data:`MCP_SERVER_NAME_MAX_LEN`.

    Registration only (``Kind.validate_new_name``): a server registered before
    the cap keeps its longer name and keeps working, and one arriving from
    another machine with its uid converges whatever its length.
    """
    if len(name) > MCP_SERVER_NAME_MAX_LEN:
        raise ValueError(
            f"mcp_server name {name!r} is {len(name)} characters; the limit is "
            f"{MCP_SERVER_NAME_MAX_LEN}, so that its tools' client-visible names "
            "(mcp__coffer__<server>__<tool>) stay within the 64 characters "
            "model provider APIs accept"
        )


def make_mcp_kind(supervisor_for: dict[str, SubprocessSupervisor]) -> Kind:
    """Construct the `mcp_server` Kind with its lifecycle + name-validation hooks.

    `supervisor_for` is a process-local registry of session-id -> supervisor.
    Every lifecycle hook walks it and evicts the matching server from every live
    session: ``on_delete`` because the registration is going away, ``on_enabled_changed``
    because a disabled server's subprocess should not outlive the switch, and
    ``on_update_config`` because a cached connection was built from the old
    config. Only the sessions in this registry are reachable — a supervisor the
    composition root builds and does not register (the process-wide one behind
    the management routes) is invisible to every hook.
    """

    async def on_delete(resource: Resource) -> None:
        # Async hook AWAITED by ResourceService.delete BEFORE the row
        # is removed, so every live session's upstream connection for this
        # server is fully evicted before deletion completes — no in-flight call
        # can outlive the registration and leak the subprocess.
        #
        # Evicted by NAME because that is what a supervisor keys its live
        # connections on: the downstream client speaks namespaced wire names
        # (``<server>__<tool>``), so the whole session-side routing path — the
        # supervisor's entries, the discovery caches, the notification
        # subscriptions — is keyed on the label the client used. The identity is
        # ``resource.uid``; the label is how a live connection is found.
        await _evict_everywhere(resource.name)

    async def _evict_everywhere(name: str) -> None:
        # Every live session's connection for ``name``, each supervisor's
        # failure suppressed so one broken session cannot keep the rest holding
        # a connection they should have dropped.
        for supervisor in list(supervisor_for.values()):
            with contextlib.suppress(Exception):
                await supervisor.evict(name)

    async def on_enabled_changed(resource: Resource) -> None:
        """Drop every live connection to a server that was just disabled.

        The gateway refuses a disabled server per call (``gateway_handlers``),
        so this is not what stops the calls — it is what stops the subprocess.
        Without it a session that had spawned the server keeps it running until
        the session ends, for a registration the user switched off. Re-enabling
        needs nothing: the next call spawns afresh.
        """
        if not resource.enabled:
            await _evict_everywhere(resource.name)

    async def on_update_config(before: Resource, _proposed: dict[str, Any]) -> None:
        """Drop every live connection so the next call spawns with the new config.

        A supervisor caches a healthy connection and never re-reads the row, so
        without this an edited command, URL or environment only took effect in
        sessions started after the edit.

        This is the only config hook the ``Kind`` record offers, and it runs
        BEFORE the write. That leaves a narrow race: a call landing between this
        eviction and the commit respawns from the row as it still stands, and
        that connection — built from the old config — stays cached until the
        next eviction. Accepted rather than closed with a post-write hook, as
        the window is one database write wide and the next edit, disable,
        crash or session end clears it.
        """
        await _evict_everywhere(before.name)

    return Kind(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        on_delete=on_delete,
        on_enabled_changed=on_enabled_changed,
        on_update_config=on_update_config,
        validate_name=_validate_mcp_name,
        validate_new_name=_cap_new_mcp_name,
        # The name prefixes every tool name an agent sees
        # (``mcp__coffer__<server>__<tool>``), and agents' permission rules and
        # skills quote those names, so a registered server's name never changes
        # (ADR names-visible-to-agents-are-fixed). A new name means
        # registering the server again; there is no display title beside it.
        name_fixed=True,
        name_fixed_resets="its capability toggles and its reach (enabled and scope)",
        titled=False,
        audit_redactor=_mcp_audit_redactor,
        secret_ref_extractor=_mcp_secret_ref_extractor,
        # Per-agent scope: the gateway filters a scoped server's tools by the
        # session's self-reported agent identity.
        supports_scope=True,
    )
