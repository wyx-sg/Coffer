"""POST /api/v1/resources/mcp_server/test-config — test a config that is not saved.

Spec mcp-gateway "Test an unsaved server config before adding it". The Add
dialog tests what the person typed before Add server: a stdio server is started
for the length of the test, an HTTP one is connected to, its tools are listed
and the tail of its stderr kept — and then everything is discarded. Nothing is
persisted: no resource, no health row, no invocation, no audit event.

Two rules keep the test from being a way around the rest of the gateway:

- A URL the person typed passes the SSRF guard before any request (Principles
  "Network defaults"); a loopback or private server is tested once it is added.
- A stored secret is released only to a registered destination whose binding a
  person approved (spec mcp-gateway "Spawn a server with a secret only once its
  binding is approved"), so a config citing ``secret_refs`` is not started;
  only values typed into the form for this test are applied.

The test stops when the client goes away: the request is watched while the
probe runs, and a disconnect cancels it, which stops the server's process group.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from fastapi import APIRouter, Depends, Request

from coffer.domain.auth_scheme import with_schemes
from coffer.domain.mcp.probe import secret_looking, secret_values
from coffer.domain.mcp.server_config import HttpTransport
from coffer.infrastructure.mcp.probe import UrlGuard, probe_server
from coffer.infrastructure.net.ssrf_guard import check_url
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.mcp.handoff_views import unsaved_test_prompt
from coffer.surfaces.http.mcp.probe_schemas import (
    McpConfigTestIn,
    McpTestHttpIn,
    McpTestResultOut,
    result_out,
)

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)

#: Failures that depend on this machine — the launcher is missing, the process
#: fails to start or exits, the network refuses or times out — and so go to an
#: agent. Not auth rejected, a stored secret, or what the server itself answers.
_MACHINE_CODES = frozenset({"spawn_failed", "exited", "timeout", "connect_failed"})

#: How often the route checks whether the client is still there.
_DISCONNECT_POLL_SECONDS = 0.25


def get_url_guard() -> UrlGuard:
    """The SSRF guard a typed URL passes; a test overrides it to reach a local fake."""
    return check_url


async def cancel_on_disconnect[T](request: Request, work: Awaitable[T]) -> T:
    """Run ``work``; cancel it (and re-raise) if the client disconnects first."""
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=_DISCONNECT_POLL_SECONDS)
            if done:
                return task.result()
            if await request.is_disconnected():
                task.cancel()
                await asyncio.wait({task})
                raise asyncio.CancelledError
    finally:
        if not task.done():
            task.cancel()
            await asyncio.wait({task})


@router.post("/test-config", response_model=McpTestResultOut)
async def test_mcp_server_config(
    body: McpConfigTestIn,
    request: Request,
    url_guard: UrlGuard = Depends(get_url_guard),  # noqa: B008
) -> McpTestResultOut:
    """Test a config without registering it; persists nothing."""
    if body.transport.secret_refs:
        keys = sorted(body.transport.secret_refs)
        return McpTestResultOut(
            ok=False,
            latency_ms=0,
            error_code="stored_secret_not_released",
            error_message=(
                "A stored secret is released only to a server that is added and "
                f"approved, so this config is tested after Add ({', '.join(keys)})."
            ),
            unreleased_secret_keys=keys,
        )
    transport = body.transport.to_transport()
    typed = dict(body.secret_values)
    # Every value worth hiding: the typed secrets, plus any plain value whose
    # key looks secret (a token pasted into an ordinary row).
    plain = transport.headers if isinstance(transport, HttpTransport) else transport.env
    hidden = secret_values([*typed.values(), *secret_looking(plain)])
    if isinstance(body.transport, McpTestHttpIn):
        # A typed header secret is the key alone; its row's scheme goes in front.
        typed = with_schemes(typed, body.transport.auth_schemes)
    result = await cancel_on_disconnect(
        request,
        probe_server(
            transport,
            typed,
            spawn_timeout_seconds=body.spawn_timeout_seconds,
            request_timeout_seconds=body.request_timeout_seconds,
            secrets=hidden,
            server_name=body.name or "test",
            url_guard=url_guard if isinstance(transport, HttpTransport) else None,
        ),
    )
    if result.ok or result.error_code not in _MACHINE_CODES:
        return result_out(result)
    # Names only: the typed secret values and the stored refs never reach the prompt.
    config = {"transport": body.transport.model_dump(exclude={"secret_refs"}, mode="json")}
    prompt = await asyncio.to_thread(
        unsaved_test_prompt,
        name=body.name or "this server",
        config=config,
        error=result.error_message,
        stderr=list(result.stderr_tail),
    )
    return result_out(result, handoff=HandoffOut(prompt=prompt))


__all__ = ["cancel_on_disconnect", "get_url_guard", "router"]
