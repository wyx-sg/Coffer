"""MCP-specific Kind wiring used by the composition root."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, Resource

_logger = logging.getLogger(__name__)

# Keys inside ``transport`` whose values may carry auth material (custom
# headers, raw environment overlays). credential_refs (keychain ref strings
# only) survive audit; the raw maps are stripped.
_AUDIT_STRIP_TRANSPORT_KEYS: frozenset[str] = frozenset({"env", "headers"})


def _mcp_audit_redactor(config: dict[str, Any]) -> dict[str, Any]:
    """Strip auth-bearing maps from an mcp_server config before audit.

    Clients can paste custom auth headers / env vars into MCP server config
    (e.g. an Authorization header on an HTTP transport). Those are materialised
    at spawn time from the keychain, but a careless user might paste the raw
    secret in instead — and we don't want it landing verbatim in
    audit_log.details_json. Stripping the structural maps keeps audit useful
    (credential_refs survive; users still see *what* changed) without ever
    persisting the secret material itself.
    """
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return config
    sanitised = {k: v for k, v in transport.items() if k not in _AUDIT_STRIP_TRANSPORT_KEYS}
    return {**config, "transport": sanitised}


def _mcp_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Pull ``transport.credential_refs`` out of a validated mcp_server config."""
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return {}
    refs = transport.get("credential_refs")
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


def make_mcp_kind(supervisor_for: dict[str, SubprocessSupervisor]) -> Kind:
    """Construct the `mcp_server` Kind with its lifecycle + name-validation hooks.

    `supervisor_for` is a process-local registry of session-id -> supervisor.
    Every lifecycle hook walks it and evicts the matching server from every live
    session: ``on_delete`` because the registration is going away, ``on_rename``
    because the key those connections are held under is, ``on_enabled_changed``
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

    async def on_rename(resource: Resource, _new_name: str) -> None:
        """Release every live connection held under the name being left behind.

        A supervisor keys its entries — and the upstream subprocess each one
        owns — on the server's NAME, because that is the vocabulary the
        downstream client speaks (``<server>__<tool>``). The row's name is about
        to change, and nothing will ever ask for the old one again: the entry
        becomes unreachable, its subprocess survives until the session disposes,
        and the next call under the new name starts a SECOND one.

        This defect is created by the change that introduced this hook. Until a
        resource's identity became its uid, ``mcp_server`` had no rename at all,
        so the stranded entry was not something a user could produce. Making
        rename available to every kind is what makes it reachable, which is why
        the fix belongs here rather than in a follow-up.

        Pre-write, and it must be: the current name is the only key that still
        reaches those connections, so they have to be released while the row
        still carries it.

        **A failure aborts the rename** — the one place this hook deliberately
        differs from ``on_delete`` above, which suppresses everything. The
        difference is not about how bad a failure is but about what the caller
        can still do with it: ``on_delete`` is a reaction to a decision already
        taken (the row is going regardless), so swallowing a broken supervisor
        keeps it from blocking the others' cleanup and the deletion itself. Here
        the write has not happened, so refusing is a real option — and it is the
        better one, because leaving the old name in place keeps the live
        subprocess addressable. Renaming anyway would trade a recoverable
        failure for an orphaned process nobody can reach.

        Partially-evicted sessions are not a problem worth avoiding: eviction
        only drops a cached connection, and the very next call through that
        session spawns a fresh one under the name it already used. So we try
        every supervisor — leaving less to redo on the retry — and re-raise the
        first failure once they have all been attempted. The exception is passed
        through as it came rather than dressed as a domain error: ``evict``
        already suppresses every failure a live connection can legitimately
        produce, so anything still escaping it is a fault in Coffer, and a fault
        should not read like something the user did.
        """
        first_error: Exception | None = None
        for session_id, supervisor in list(supervisor_for.items()):
            try:
                await supervisor.evict(resource.name)
            except Exception as e:
                _logger.exception(
                    "mcp.kind.rename_evict_failed",
                    extra={"server": resource.name, "session": session_id},
                )
                if first_error is None:
                    first_error = e
        if first_error is not None:
            raise first_error

    return Kind(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        on_delete=on_delete,
        on_rename=on_rename,
        on_enabled_changed=on_enabled_changed,
        on_update_config=on_update_config,
        validate_name=_validate_mcp_name,
        audit_redactor=_mcp_audit_redactor,
        credential_ref_extractor=_mcp_credential_ref_extractor,
        # Per-agent scope: the gateway filters a scoped server's tools by the
        # session's self-reported agent identity.
        supports_scope=True,
    )
