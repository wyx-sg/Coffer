"""Stdio upstream connection — async wrapper around an mcp ClientSession.

Spawns the upstream as a child subprocess with the env we hand it (which
will already contain materialised credentials from CredentialResolver).
The lifecycle is:
    create -> spawn_and_initialize -> [request*] -> close
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from typing import Any

import psutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.session import ListRootsFnT, SamplingFnT
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.types import ServerNotification

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import StdioTransport
from coffer.infrastructure.daemon.orphan_sweep import reap_pidfile, record_spawn

NotificationCallback = Callable[[Any], Awaitable[None]]

# CODE-028: serialise the "snapshot children → spawn → diff" window across the
# whole process. Each session owns its own supervisor whose spawn_lock is
# per-(supervisor, server), so without a process-wide lock two concurrent
# spawns from different sessions can interleave their before/after snapshots
# and mis-attribute (or miss) each other's child PID. Held only around the
# narrow spawn window, never across MCP initialize.
_SPAWN_SNAPSHOT_LOCK = asyncio.Lock()


class StdioUpstreamConnection:
    """One open stdio session with one upstream MCP server."""

    def __init__(
        self,
        transport: StdioTransport,
        env_overlay: dict[str, str],
        spawn_timeout_seconds: int = 30,
        request_timeout_seconds: int = 120,
        server_name: str = "upstream",
    ) -> None:
        self._transport = transport
        self._env_overlay = env_overlay
        self._spawn_timeout = spawn_timeout_seconds
        self._request_timeout = request_timeout_seconds
        self._server_name = server_name

        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._notification_callback: NotificationCallback | None = None
        # Server-initiated request callbacks (T-061/T-062)
        self._sampling_callback: SamplingFnT | None = None
        self._list_roots_callback: ListRootsFnT | None = None
        # PID-file paths written by record_spawn; cleared on close.
        self._pid_files: list[Path] = []

    def on_notification(self, cb: NotificationCallback) -> None:
        """Register a callback that receives every notification from the upstream."""
        self._notification_callback = cb

    def on_sampling_request(self, cb: SamplingFnT) -> None:
        """Register a callback that handles sampling/createMessage requests from the upstream."""
        self._sampling_callback = cb

    def on_roots_request(self, cb: ListRootsFnT) -> None:
        """Register a callback that handles roots/list requests from the upstream."""
        self._list_roots_callback = cb

    async def _message_handler(
        self,
        message: Any,
    ) -> None:
        """Forward ServerNotifications to the registered callback."""
        if isinstance(message, ServerNotification) and self._notification_callback is not None:
            with suppress(Exception):
                await self._notification_callback(message)

    async def spawn_and_initialize(self) -> dict[str, Any]:
        """Spawn the subprocess + complete MCP initialize.

        Returns the server's capabilities as a plain dict.
        """
        # CODE-027: build the child env from the SDK's minimal safe allowlist
        # (PATH/HOME/SHELL/… — what a server legitimately needs to run) plus
        # ONLY this server's static env and materialised credentials. We must
        # NOT inherit the daemon's full ``os.environ``: an untrusted upstream
        # server would otherwise be able to read every secret/token the daemon
        # was started with (AWS keys, other services' tokens, COFFER_* config),
        # defeating the keychain-scoped credential isolation. Passing an explicit
        # ``env`` also bypasses stdio_client's own filter, so our additions
        # (including secrets) survive intact.
        env = {**get_default_environment(), **self._transport.env, **self._env_overlay}

        params = StdioServerParameters(
            command=self._transport.command,
            args=self._transport.args,
            env=env,
            cwd=self._transport.cwd,
        )

        self._exit_stack = AsyncExitStack()
        try:
            # --- PID snapshot (T-051, hardened in CODE-028) ---
            # Snapshot this daemon's children BEFORE letting the SDK spawn the
            # upstream subprocess, then diff after stdio_client opens to learn
            # the new child PID(s). This diff-snapshot approach is used because
            # mcp.client.stdio.stdio_client manages the subprocess internally
            # and doesn't expose the PID.
            #
            # CODE-028: serialise the snapshot+spawn+diff under a process-wide
            # lock so concurrent spawns from OTHER sessions' supervisors can't
            # interleave the snapshot window and steal/miss each other's PID.
            # We hold the lock only across the spawn itself (not initialize).
            self_proc = psutil.Process()
            async with _SPAWN_SNAPSHOT_LOCK:
                children_before = {c.pid for c in self_proc.children(recursive=False)}

                read, write = await asyncio.wait_for(
                    self._exit_stack.enter_async_context(stdio_client(params)),
                    timeout=self._spawn_timeout,
                )

                # Snapshot after — new PIDs belong to the SDK's spawn. Record a
                # PID file for EVERY new child, not just ones whose cmdline[0]
                # equals the configured command: servers launched via a wrapper
                # (npx/uv/node) have a resolved-interpreter cmdline that never
                # matches the bare command, and skipping them left real orphans
                # untracked. record_spawn stores the child's actual cmdline so
                # sweep_orphans can still guard against PID recycling.
                children_after = {c.pid for c in self_proc.children(recursive=False)}
                new_pids = children_after - children_before

                self._pid_files = []
                for new_pid in new_pids:
                    try:
                        cmd = psutil.Process(new_pid).cmdline()
                        self._pid_files.append(record_spawn(self._server_name, new_pid, cmd))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            # --- end PID snapshot ---

            session = ClientSession(
                read,
                write,
                message_handler=self._message_handler,
                sampling_callback=self._sampling_callback,
                list_roots_callback=self._list_roots_callback,
            )
            await asyncio.wait_for(
                self._exit_stack.enter_async_context(session),
                timeout=self._spawn_timeout,
            )
            init_result = await asyncio.wait_for(
                session.initialize(),
                timeout=self._spawn_timeout,
            )
        except TimeoutError as exc:
            await self._cleanup()
            raise UpstreamTimeout(f"upstream init exceeded {self._spawn_timeout}s") from exc
        except Exception as exc:
            await self._cleanup()
            # CODE-039: don't interpolate the raw exception into the message —
            # an upstream/transport error can embed credential-bearing argv or
            # env detail. Surface only the exception type; the original is
            # chained via ``from exc`` for a debugger but never stringified
            # into logs or API responses.
            raise UpstreamUnavailable(f"upstream init failed: {type(exc).__name__}") from exc

        self._session = session

        try:
            capabilities: dict[str, Any] = init_result.capabilities.model_dump()
        except AttributeError:
            capabilities = {}
        return capabilities

    async def request(
        self,
        method: str,
        params: dict[str, Any],
        progress_callback: Any | None = None,
    ) -> Any:
        """Forward a single MCP request, with timeout. Returns the SDK result object."""
        if self._session is None:
            raise UpstreamUnavailable("upstream not initialized")
        try:
            return await asyncio.wait_for(
                self._dispatch_method(method, params, progress_callback=progress_callback),
                timeout=self._request_timeout,
            )
        except TimeoutError as exc:
            raise UpstreamTimeout(f"upstream {method} exceeded {self._request_timeout}s") from exc

    async def _dispatch_method(
        self,
        method: str,
        params: dict[str, Any],
        progress_callback: Any | None = None,
    ) -> Any:
        assert self._session is not None
        if method == "tools/list":
            return await self._session.list_tools()
        if method == "tools/call":
            # T-060: pass read_timeout_seconds so the SDK resets the idle timer
            # on every notifications/progress event, preventing premature timeout
            # of long-running tools that stream progress.
            from datetime import timedelta

            try:
                return await self._session.call_tool(
                    params["name"],
                    arguments=params.get("arguments"),
                    read_timeout_seconds=timedelta(seconds=self._request_timeout),
                    progress_callback=progress_callback,
                )
            except TypeError:
                # Older SDK build that doesn't accept read_timeout_seconds
                return await self._session.call_tool(
                    params["name"], arguments=params.get("arguments")
                )
        if method == "resources/list":
            return await self._session.list_resources()
        if method == "resources/read":
            return await self._session.read_resource(params["uri"])
        if method == "prompts/list":
            return await self._session.list_prompts()
        if method == "prompts/get":
            return await self._session.get_prompt(params["name"], arguments=params.get("arguments"))
        raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")

    async def close(self) -> None:
        """Close the upstream connection gracefully."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        if self._exit_stack is not None:
            with suppress(TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._exit_stack.aclose(), timeout=5.0)
            self._exit_stack = None

        # Belt-and-braces against leaked upstream processes (T-051). aclose()
        # normally tears down the upstream subprocess tree, but when a
        # long-running upstream write hangs the SDK teardown the child survives
        # and accumulates across reconnects. reap_pidfile authoritatively kills
        # each recorded PID *and its descendants* if still alive, then removes
        # the tracking file; it no-ops on already-dead PIDs, so the graceful
        # path is unaffected. (Replaces the old startup-only orphan sweep as the
        # primary guard — that sweep never fired on a long-lived daemon.)
        #
        # reap_pidfile blocks (psutil.wait_procs up to ~2s when a wedged child
        # must be escalated to SIGKILL), so run it off the event loop — this
        # teardown can fire from evict() inside a live request path.
        loop = asyncio.get_running_loop()
        for path in self._pid_files:
            await loop.run_in_executor(None, reap_pidfile, path)
        self._pid_files = []

        self._session = None
