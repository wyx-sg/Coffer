"""Gateway session plumbing: bad upstream results, echoed ids, disposal.

Three separate ways a long-lived gateway session leaks or wedges, each pinned
here because none of them shows up as an error at the point of the bug — they
show up later as a hang, a timeout, or a process that never gets reaped.
"""

from __future__ import annotations

import asyncio


async def test_an_unparseable_upstream_result_becomes_upstream_unavailable() -> None:
    """A result the gateway cannot read is an UPSTREAM failure, not an internal
    one: it must surface as `UpstreamUnavailable` (which the caller can retry
    and which names the server) rather than blow up as a TypeError halfway
    through serialising a response.
    """
    import pytest

    from coffer.application.mcp.gateway_handlers import coerce_call_result
    from coffer.domain.errors import UpstreamUnavailable

    # A well-formed result goes through untouched.
    assert coerce_call_result({"content": []}) == {"content": []}
    with pytest.raises(UpstreamUnavailable):
        coerce_call_result(object())


async def test_a_request_id_echoed_back_as_a_string_still_resolves() -> None:
    """JSON-RPC ids are compared by VALUE, not by type.

    The gateway sends integer ids, but a downstream client may echo one back as
    a string. If the registry matched on type as well, the pending request
    would never resolve — the caller would block until its timeout and the
    failure would look like an unresponsive client rather than an id mismatch.
    """
    from coffer.application.mcp.gateway_server_requests import ServerRequestRegistry

    reg = ServerRequestRegistry()
    sent: dict[str, object] = {}

    async def sink(payload: dict[str, object]) -> None:
        sent.update(payload)

    task = asyncio.create_task(reg.send_request("roots/list", {}, sink, timeout=5.0))
    for _ in range(50):
        await asyncio.sleep(0)
        if "id" in sent:
            break
    assert "id" in sent
    rid = sent["id"]
    assert isinstance(rid, int)

    # Client echoes the id back as a STRING.
    matched = reg.handle_response({"id": str(rid), "result": {"roots": []}})
    assert matched is True
    assert await task == {"roots": []}


async def test_disposing_a_session_runs_its_on_dispose_hook() -> None:
    """Disposal has to reach the composition root, or the session's supervisor
    stays in the registry after the session is gone — a leak that keeps
    upstream subprocesses alive for the life of the daemon.
    """
    from coffer.application.mcp.gateway import MCPGatewaySession

    class _StubSupervisor:
        async def dispose(self) -> None:
            return None

    registry: dict[str, object] = {}
    session = MCPGatewaySession(
        session_id="s1",
        resource_service=object(),  # type: ignore[arg-type]
        supervisor=_StubSupervisor(),  # type: ignore[arg-type]
        discovery=object(),  # type: ignore[arg-type]
        preferences=object(),  # type: ignore[arg-type]
        invocations=object(),  # type: ignore[arg-type]
        on_dispose=lambda: registry.pop("s1", None),
    )
    registry["s1"] = object()
    await session.dispose()
    assert "s1" not in registry, "on_dispose must remove the registry entry"
