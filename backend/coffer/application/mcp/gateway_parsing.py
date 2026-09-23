"""Module-level parsing helpers for the MCP gateway session.

Extracted from `gateway.py` to keep that file under the project's 400-LOC
ceiling. These are pure functions over the loosely-typed envelopes the gateway
receives — the agent's launch cwd from an ``initialize`` handshake, and the
method/params of an upstream notification (whose shape varies by SDK version).
"""

from __future__ import annotations

from typing import Any

#: The extension key the shim stamps the launch cwd into (initialize handshake).
_CWD_META_KEY = "coffer/cwd"
#: The extension key the shim stamps its self-reported agent identity into (spec
#: mcp-gateway "Take the agent identity from the handshake"). The value is the agent
#: resource's **uid**, which is also why the key is not the older ``coffer/agent``: that
#: one carried a name, and a shim installed by an older Coffer is still out there
#: sending it. Reading only the new key is what makes such a shim *unidentified* rather
#: than quietly matched against a scope by a stale label (ADR
#: resource-identity-is-an-immutable-uid; "no name fallback").
_AGENT_UID_META_KEY = "coffer/agent-uid"


def _extract_cwd(params: dict[str, Any]) -> str | None:
    """Pull the agent's launch cwd from an ``initialize`` envelope's
    ``params._meta["coffer/cwd"]`` (set by the shim). Absent → None."""
    meta = params.get("_meta")
    if isinstance(meta, dict):
        cwd = meta.get(_CWD_META_KEY)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def _extract_agent_uid(params: dict[str, Any]) -> str | None:
    """Pull the shim's self-reported agent uid from an ``initialize`` envelope's
    ``params._meta["coffer/agent-uid"]`` (set by the shim when it was launched
    with ``--agent-uid <uid>``). Absent → None, i.e. an unidentified session,
    which then matches unscoped resources only."""
    meta = params.get("_meta")
    if isinstance(meta, dict):
        agent_uid = meta.get(_AGENT_UID_META_KEY)
        if isinstance(agent_uid, str) and agent_uid:
            return agent_uid
    return None


def _extract_method(notification: Any) -> str | None:
    """Defensive extraction — the SDK wraps notifications in various shapes."""
    m = getattr(notification, "method", None)
    if m is not None:
        return str(m)
    root = getattr(notification, "root", None)
    if root is not None:
        # CODE-032: coerce to str like the branch above. The SDK may expose
        # ``root.method`` as an enum/Pydantic value; comparing that to the
        # plain string literals in _on_upstream_notification would never match,
        # silently dropping list_changed invalidation + forwarding.
        rm = getattr(root, "method", None)
        return str(rm) if rm is not None else None
    if isinstance(notification, dict):
        return notification.get("method")
    return None


def _extract_params(notification: Any) -> dict[str, Any] | None:
    p = getattr(notification, "params", None)
    if p is None:
        root = getattr(notification, "root", None)
        if root is not None:
            p = getattr(root, "params", None)
    if p is None and isinstance(notification, dict):
        p = notification.get("params")
    if p is None:
        return None
    if hasattr(p, "model_dump"):
        result: dict[str, Any] = p.model_dump(exclude_none=True, by_alias=True)
        return result
    if isinstance(p, dict):
        return p
    return None
