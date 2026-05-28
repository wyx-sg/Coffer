"""Stdio upstream connection — async wrapper around an mcp ClientSession.

Spawns the upstream as a child subprocess with the env we hand it (which
will already contain materialised credentials from CredentialResolver).
The lifecycle is:
    create -> spawn_and_initialize -> [request*] -> close
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from typing import Any

import psutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.session import ListRootsFnT, SamplingFnT
from mcp.client.stdio import stdio_client
from mcp.types import ServerNotification

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import StdioTransport
from coffer.infrastructure.daemon.orphan_sweep import forget_spawn, record_spawn

NotificationCallback = Callable[[Any], Awaitable[None]]


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
        # Build the env: inherit the daemon's environment, then layer the
        # overlays (which include both static env from config and materialised
        # credentials).  We pass the full merged dict as server.env so that
        # stdio_client will use {get_default_environment(), **our_env} — this
        # ensures our additions (including secrets) survive the SDK's safe-env
        # filter.
        env = {**os.environ, **self._transport.env, **self._env_overlay}

        params = StdioServerParameters(
            command=self._transport.command,
            args=self._transport.args,
            env=env,
            cwd=self._transport.cwd,
        )

        self._exit_stack = AsyncExitStack()
        try:
            # --- PID snapshot (T-051) ---
            # Snapshot current children of this daemon process BEFORE letting
            # the SDK spawn the upstream subprocess.  After stdio_client opens,
            # diff the two snapshots to discover the new child PID.
            #
            # This is intentionally a "diff-snapshot" rather than direct spawn
            # because mcp.client.stdio.stdio_client manages the subprocess
            # internally and doesn't expose the PID.  The approach is safe here
            # because SubprocessSupervisor._build_connection holds a per-server
            # lock, so spawns are serialised and only one new child appears.
            # (A future refactor could bypass stdio_client entirely and call
            # asyncio.create_subprocess_exec directly to capture the PID cleanly.)
            self_proc = psutil.Process()
            children_before = {c.pid for c in self_proc.children(recursive=False)}

            read, write = await asyncio.wait_for(
                self._exit_stack.enter_async_context(stdio_client(params)),
                timeout=self._spawn_timeout,
            )

            # Snapshot after — new PIDs belong to the SDK's spawn
            children_after = {c.pid for c in self_proc.children(recursive=False)}
            new_pids = children_after - children_before

            # Record PID files for each new child whose cmdline matches the transport command.
            # Typically only one new PID; tolerate edge cases (e.g. shell wrapper = 2 children).
            expected_cmd_first = self._transport.command
            self._pid_files = []
            for new_pid in new_pids:
                try:
                    new_proc = psutil.Process(new_pid)
                    cmd = new_proc.cmdline()
                    # Match against the bare command name or a full path ending in it.
                    if cmd and (
                        cmd[0] == expected_cmd_first or cmd[0].endswith(f"/{expected_cmd_first}")
                    ):
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
            raise UpstreamUnavailable(f"upstream init failed: {exc}") from exc

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

        # Remove PID tracking files on graceful shutdown (T-051).
        # (Note: the previous "belt-and-braces SIGKILL on self._process_pid"
        # branch was dead — the field was never assigned. Removed in CODE-014.
        # The orphan-sweep at the next startup remains the authoritative
        # guard against leaked upstream processes.)
        for path in self._pid_files:
            forget_spawn(path)
        self._pid_files = []

        self._session = None
