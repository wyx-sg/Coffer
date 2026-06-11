"""MCP-specific Kind wiring used by the composition root."""

from __future__ import annotations

import contextlib
from typing import Any

from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef

# Keys inside ``transport`` whose values may carry auth material (custom
# headers, raw environment overlays). credential_refs (keychain ref strings
# only) survive audit; the raw maps are stripped. See CODE-006.
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

    CODE-030: capabilities are exposed downstream as ``<server>__<tool>`` and
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
    """Construct the `mcp_server` Kind with on_delete + name-validation hooks.

    `supervisor_for` is a process-local registry of session-id -> supervisor;
    on resource delete we walk it and evict the matching server from each
    live session. This is best-effort — sessions may not have the server
    spawned yet (no-op) or the connection may have already crashed
    (suppressed).
    """

    async def on_delete(ref: ResourceRef) -> None:
        # CODE-033: async hook AWAITED by ResourceService.delete BEFORE the row
        # is removed, so every live session's upstream connection for this
        # server is fully evicted before deletion completes — no in-flight call
        # can outlive the registration and leak the subprocess.
        for supervisor in list(supervisor_for.values()):
            with contextlib.suppress(Exception):
                await supervisor.evict(ref.name)

    return Kind(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        on_delete=on_delete,
        validate_name=_validate_mcp_name,
        audit_redactor=_mcp_audit_redactor,
        credential_ref_extractor=_mcp_credential_ref_extractor,
    )
