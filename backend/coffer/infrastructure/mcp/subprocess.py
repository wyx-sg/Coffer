"""Stdio upstream connection — async wrapper around an mcp ClientSession.

Spawns the upstream as a child subprocess with the env we hand it (which
will already contain materialised secrets from SecretResolver).
The lifecycle is:
    create -> spawn_and_initialize -> [request*] -> close
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from typing import Any, TextIO

from mcp import ClientSession, StdioServerParameters
from mcp.client.session import ListRootsFnT, SamplingFnT
from mcp.client.stdio import get_default_environment
from mcp.types import ServerNotification

from coffer.application.runtime.supervisor import spawn
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import StdioTransport
from coffer.infrastructure.daemon.orphan_sweep import reap_pidfile
from coffer.infrastructure.logging.files import LineSink, write_coffer_line
from coffer.infrastructure.mcp.dispatch import dispatch_method
from coffer.infrastructure.mcp.process_group import kill_process_group
from coffer.infrastructure.mcp.stdio_spawn import leaf_exception, open_child

NotificationCallback = Callable[[Any], Awaitable[None]]

# How long close() waits for the lifetime task to unwind before cancelling it.
_TEARDOWN_SECONDS = 12.0


class StdioUpstreamConnection:
    """One open stdio session with one upstream MCP server."""

    def __init__(
        self,
        transport: StdioTransport,
        env_overlay: dict[str, str],
        spawn_timeout_seconds: int = 30,
        request_timeout_seconds: int = 120,
        server_name: str = "upstream",
        server_uid: str = "",
        *,
        stderr_sink: TextIO | None = None,
        kill_group_on_close: bool = False,
    ) -> None:
        self._transport = transport
        self._env_overlay = env_overlay
        self._spawn_timeout = spawn_timeout_seconds
        self._request_timeout = request_timeout_seconds
        # Two values, two jobs. ``_server_name`` is the label: it titles this
        # upstream's stderr file and every timeout message a user reads.
        # ``_server_uid`` is the identity the PID files are recorded under, so a
        # leaked child is still attributable to the same registration after the
        # user renames it (ADR identity-is-the-uid-inside-the-file). It
        # defaults to empty for a hand-built connection in a test that spawns
        # nothing it cares to attribute; ``record_spawn`` then writes the file
        # under the empty identity, which still reaps by pid + cmdline.
        self._server_name = server_name
        self._server_uid = server_uid
        # A one-off test (``probe.py``) hands its own stderr sink, which it
        # reads back, instead of the server's log file; Coffer writes none of
        # its own start / stop lines into it. It also asks for the whole
        # process group to be stopped on close: the SDK signals the group only
        # when the leader outlives stdin closing, so a leader that exits and
        # leaves a grandchild behind would otherwise leak it.
        self._stderr_sink = stderr_sink
        self._kill_group_on_close = kill_group_on_close
        self._child_pids: list[int] = []

        # The lifetime task owning the child and its anyio scopes, and the event
        # ``close`` pokes it with.
        self._runner: asyncio.Task[None] | None = None
        self._close_event: asyncio.Event | None = None
        self._ready: asyncio.Future[Any] | None = None
        self._errlog: LineSink | None = None
        self._session: ClientSession | None = None
        self._notification_callback: NotificationCallback | None = None
        # Server-initiated request callbacks (sampling and roots)
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

        Returns the server's capabilities as a plain dict. The whole phase is
        bounded by ``spawn_timeout_seconds``, measured here while waiting on the
        lifetime task's ready-future — the same shape as the HTTP adapter.
        """
        # Build the child env from the SDK's minimal safe allowlist
        # (PATH/HOME/SHELL/… — what a server legitimately needs to run) plus
        # ONLY this server's static env and materialised secrets. We must
        # NOT inherit the daemon's full ``os.environ``: an untrusted upstream
        # server would otherwise be able to read every secret/token the daemon
        # was started with (AWS keys, other services' tokens, COFFER_* config),
        # defeating the keychain-scoped secret isolation. Passing an explicit
        # ``env`` also bypasses stdio_client's own filter, so our additions
        # (including secrets) survive intact.
        env = {**get_default_environment(), **self._transport.env, **self._env_overlay}
        params = StdioServerParameters(
            command=self._transport.command,
            args=self._transport.args,
            env=env,
            cwd=self._transport.cwd,
        )

        loop = asyncio.get_running_loop()
        ready: asyncio.Future[Any] = loop.create_future()
        # Whoever waited may have left (the caller was cancelled): an outcome
        # nobody reads is not an error worth a "never retrieved" warning.
        ready.add_done_callback(lambda f: f.cancelled() or f.exception())
        close_event = asyncio.Event()
        self._close_event = close_event
        self._ready = ready
        self._runner = spawn(
            self._run_lifetime(params, env, ready, close_event),
            name=f"coffer-mcp-stdio-upstream:{self._server_name}",
        )
        try:
            # asyncio.wait (not wait_for) neither cancels the future nor
            # re-raises its exception, so the outcome is classified below.
            done, _pending = await asyncio.wait({ready}, timeout=float(self._spawn_timeout))
        except asyncio.CancelledError:
            # The caller gave up (the listing budget, a shutdown): the child may
            # already be running, so tear it down before the cancel moves on.
            with suppress(Exception):
                await self._cleanup()
            raise
        if not done:
            self._note_error(f"error did not start within {self._spawn_timeout}s")
            await self._cleanup()
            raise UpstreamTimeout(
                f"MCP server {self._server_name!r} did not finish starting within "
                f"{self._spawn_timeout}s (its spawn timeout)"
            )
        if ready.cancelled():
            await self._cleanup()
            raise UpstreamUnavailable("upstream init cancelled: CancelledError")
        exc = ready.exception()
        if exc is not None:
            # The lifetime task has already written why it failed to the log
            # (before unwinding closed it) — see ``_run_lifetime``.
            leaf = leaf_exception(exc)
            await self._cleanup()
            # Don't interpolate the raw exception into the message — an
            # upstream/transport error can embed secret-bearing argv or env
            # detail. Surface only the exception type; the original is chained
            # via ``from exc`` for a debugger but never stringified into logs or
            # API responses.
            raise UpstreamUnavailable(f"upstream init failed: {type(leaf).__name__}") from exc

        init_result = ready.result()
        try:
            capabilities: dict[str, Any] = init_result.capabilities.model_dump(by_alias=True)
        except AttributeError:
            capabilities = {}
        return capabilities

    def _note_error(self, line: str) -> None:
        if self._errlog is not None:
            write_coffer_line(self._errlog, line)

    async def _run_lifetime(
        self,
        params: StdioServerParameters,
        env: dict[str, str],
        ready: asyncio.Future[Any],
        close_event: asyncio.Event,
    ) -> None:
        """Own the child process, its pipes and the ClientSession for the
        connection's whole life.

        Runs as its own task so every anyio cancel scope the SDK opens is entered
        and exited by this task, in order — however many other tasks (a gather
        child, the recovery task, a request task) later call ``close``. Publishes
        the initialize result (or the failure) on ``ready``, parks until
        ``close_event`` is set, and unwinds the contexts here.
        """
        exit_stack = AsyncExitStack()
        session: ClientSession | None = None
        init_error: BaseException | None = None
        init_result: Any = None
        try:
            try:
                started = await open_child(
                    exit_stack,
                    params,
                    server_name=self._server_name,
                    server_uid=self._server_uid,
                    stderr_sink=self._stderr_sink,
                    command_line=self._command_line(),
                    on_stop=self._note_stop,
                    # Only the secret overlay is masked out of stderr, not the
                    # server's static env (spec secret "Hold plaintext only in
                    # memory at the moment of use").
                    mask_values=self._env_overlay.values(),
                    on_sink=self._set_errlog,
                )
                self._pid_files = started.pid_files
                self._child_pids = started.child_pids
                session = await exit_stack.enter_async_context(
                    ClientSession(
                        started.read,
                        started.write,
                        message_handler=self._message_handler,
                        sampling_callback=self._sampling_callback,
                        list_roots_callback=self._list_roots_callback,
                    )
                )
                init_result = await session.initialize()
            except (Exception, asyncio.CancelledError) as exc:
                init_error = exc

            if init_error is None:
                self._session = session
                if not ready.done():
                    ready.set_result(init_result)
                with suppress(asyncio.CancelledError):
                    await close_event.wait()
        finally:
            if init_error is not None and not isinstance(init_error, asyncio.CancelledError):
                # Written here, while the log is still open: unwinding the
                # stack below closes it.
                self._note_error(self._launch_error_line(leaf_exception(init_error), env))
            close_error: BaseException | None = None
            try:
                # aclose() drives stdio_client's teardown, whose FINAL step
                # closes the two daemon-side pipe fds. It is internally bounded
                # (the SDK waits ~2s for the child to exit after stdin closes,
                # then SIGTERM -> SIGKILL with its own 2s grace), so 10s clears
                # it with margin; the cap only trips for a wedged teardown, which
                # the pid-file reap in ``_cleanup`` then covers.
                await asyncio.wait_for(exit_stack.aclose(), timeout=10.0)
            except (Exception, asyncio.CancelledError, BaseExceptionGroup) as exc:
                close_error = exc
            if self._session is session:
                self._session = None
            if not ready.done():
                publish = init_error
                if isinstance(publish, asyncio.CancelledError) and close_error is not None:
                    publish = close_error
                if publish is None:
                    ready.cancel()
                else:
                    ready.set_exception(publish)

    def _command_line(self) -> str:
        """The launcher and its static args. Secrets never appear here: they
        reach the child only through ``secret_refs`` in its environment."""
        return " ".join([self._transport.command, *self._transport.args])

    def _set_errlog(self, errlog: LineSink) -> None:
        self._errlog = errlog

    def _note_stop(self, errlog: LineSink) -> None:
        # Only a session that came up is "stopped"; a failed start has its line.
        if self._session is not None:
            write_coffer_line(errlog, "stop after the session ended")

    def _launch_error_line(self, exc: BaseException, env: dict[str, str]) -> str:
        """Coffer's own account of a failed start: the exception type only (its
        text can carry argv or env detail), or the launcher that did not resolve."""
        if isinstance(exc, FileNotFoundError):
            path = env.get("PATH", "")
            return f'error launcher "{self._transport.command}" not found on PATH {path}'
        return f"error {type(exc).__name__}"

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
            raise UpstreamTimeout(
                f"MCP server {self._server_name!r} did not answer {method} within "
                f"{self._request_timeout}s (its request timeout)"
            ) from exc

    async def _dispatch_method(
        self,
        method: str,
        params: dict[str, Any],
        progress_callback: Any | None = None,
    ) -> Any:
        assert self._session is not None
        return await dispatch_method(
            self._session,
            method,
            params,
            request_timeout_seconds=float(self._request_timeout),
            progress_callback=progress_callback,
        )

    async def close(self) -> None:
        """Close the upstream connection gracefully."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Stop the lifetime task (which unwinds the child and its pipes in the
        task that opened them), then reap what is left of the child itself."""
        runner, self._runner = self._runner, None
        if runner is not None:
            if self._close_event is not None:
                self._close_event.set()
            if self._ready is not None and not self._ready.done():
                # Still starting: the task is inside initialize, not parked on
                # the event, so it has to be cancelled to start unwinding.
                runner.cancel()
            done, _ = await asyncio.wait({runner}, timeout=_TEARDOWN_SECONDS)
            if not done:
                runner.cancel()
                await asyncio.wait({runner}, timeout=_TEARDOWN_SECONDS)

        # Belt-and-braces against leaked upstream processes. aclose()
        # normally tears down the upstream subprocess tree, but when a
        # long-running upstream write hangs the SDK teardown the child survives
        # and accumulates across reconnects. reap_pidfile authoritatively kills
        # each recorded PID *and its descendants* if still alive, then removes
        # the tracking file; it no-ops on already-dead PIDs, so the graceful
        # path is unaffected. (Replaces the old startup-only orphan sweep as the
        # primary guard — that sweep never fired on a long-lived daemon.)
        #
        # Called synchronously (not via run_in_executor): _cleanup must add no
        # await point after aclose(), or dispose()/evict() teardown trips
        # anyio's "cancel scope exited in a different task" during shutdown.
        # The only blocking case is a wedged child escalating SIGTERM→SIGKILL
        # (~2s), on par with the per-upstream aclose budget dispose() already
        # tolerates; the happy path returns immediately (PID already gone).
        for path in self._pid_files:
            reap_pidfile(path)
        self._pid_files = []
        if self._kill_group_on_close:
            for pgid in self._child_pids:
                kill_process_group(pgid)
        self._child_pids = []

        self._session = None
