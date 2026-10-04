"""The daemon's side of the model proxy: find or spawn it, feed it, restart it.

The proxy is a sibling process that outlives the daemon (ADR api-key-providers-
are-reached-through-a-separate-local-model-proxy, Option C): a daemon restart
or upgrade must not cut a single in-flight model stream. So :meth:`start`
first looks for a running proxy through ``proxy.json`` and RE-ATTACHES to it
when it answers ``/_coffer/health`` with the control token and is this build's
version. A proxy from another build is told to drain — it refuses new requests
and exits once its open streams finish — and a fresh one is spawned when it is
gone. :meth:`stop` deliberately leaves the proxy running.

The daemon is the only holder of the master key; the proxy gets the decrypted
keys it needs in the :class:`ProxyState` pushed over the loopback control
route — on spawn, on re-attach and on every :meth:`refresh` — and only ever in
memory. They never travel in argv, the environment or a file.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from coffer.application.runtime.supervisor import spawn
from coffer.domain.model_proxy.state import CONTROL_TOKEN_HEADER, ProxyState
from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.model_proxy.info import EXIT_PORT_IN_USE, ProxyInfo, read_info
from coffer.infrastructure.platform.process import detached_popen_kwargs

_logger = logging.getLogger(__name__)

SPAWN_TIMEOUT_SECONDS = 20.0
DRAIN_TIMEOUT_SECONDS = 30.0
_HTTP_TIMEOUT = httpx.Timeout(5.0, connect=2.0)
#: Restart backoff: the wait after the first failed start, doubled for every
#: failure that follows, up to the cap. A start that fails because the port is
#: held, or the binary is broken, will fail the same way a minute later; the
#: cap keeps trying without filling the log and spawning a process every few
#: seconds.
_BACKOFF_BASE = 5.0
_BACKOFF_MAX = 600.0
#: After this many failures in a row the supervisor reports the proxy as
#: failing (``ProxyStatus.failing``) and says so once in the log; later retries
#: are logged only when the cause changes.
FAILING_AFTER = 3
#: How long an idle supervisor (nothing is routed through the proxy, so none
#: is running) waits before it asks again, unless a state push nudges it.
_IDLE_RECHECK = 60.0


@dataclass(frozen=True)
class ProxyStatus:
    running: bool
    pid: int | None
    port: int
    version: str | None
    restarts: int
    last_error: str | None
    revision: int | None
    started_at: str | None
    #: Consecutive failed attempts to start it; ``0`` while it is up or idle.
    consecutive_failures: int = 0
    #: The start has failed ``FAILING_AFTER`` times running; retries slow down.
    failing: bool = False


def default_proxy_command(port: int) -> list[str]:
    """The frozen ``coffer-daemon proxy`` or, from source, this interpreter."""
    if getattr(sys, "frozen", False):
        return [daemon_spawn_command()[0], "proxy", "--port", str(port)]
    return [sys.executable, "-m", "coffer.infrastructure.model_proxy.entry", "--port", str(port)]


def _source_root() -> str:
    """The directory holding the imported ``coffer`` package — prefixed onto the
    child's ``PYTHONPATH`` so a worktree's proxy runs that worktree's code."""
    import coffer

    return str(Path(coffer.__file__).resolve().parent.parent)


def _pid_alive(pid: int) -> bool:
    # A proxy an earlier supervisor in this same process spawned is our child:
    # once it exits it stays a zombie — and "alive" to kill(0) — until reaped.
    with contextlib.suppress(ChildProcessError, OSError):
        os.waitpid(pid, os.WNOHANG)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ProxySupervisor:
    def __init__(
        self,
        state_provider: Callable[[], Awaitable[ProxyState]],
        *,
        port: int,
        coffer_dir: Path,
        version: str,
        command: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        interval: float = 5.0,
        spawn_timeout: float = SPAWN_TIMEOUT_SECONDS,
        drain_timeout: float = DRAIN_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._state_provider = state_provider
        self.port = port
        self.coffer_dir = coffer_dir
        self.version = version
        self._command = list(command) if command is not None else None
        self._env = dict(env) if env is not None else None
        self._interval = interval
        self._spawn_timeout = spawn_timeout
        self._drain_timeout = drain_timeout
        self._info: ProxyInfo | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._health: dict[str, Any] | None = None
        self._restarts = 0
        self._last_error: str | None = None
        self._pushed_revision: int | None = None
        self._lock = asyncio.Lock()
        self._dirty = False
        self._watchdog: asyncio.Task[None] | None = None
        self._failures = 0
        self._prefetched: ProxyState | None = None
        #: No proxy is running because no agent is routed through one.
        self._idle = False
        #: Not before this time (``clock``) is another start attempted.
        self._retry_at = 0.0
        self._http = httpx.AsyncClient(timeout=_HTTP_TIMEOUT, trust_env=False)

    # --- public ---------------------------------------------------------------------

    async def start(self) -> None:
        """Attach to a live same-version proxy, or replace/spawn one; push state;
        start the watchdog. May wait up to ``drain_timeout`` for an old build's
        proxy to finish its streams — run it in a background task if that matters."""
        try:
            if await self._attach_or_spawn():
                await self.refresh()
            else:
                self._go_idle()
        except Exception as exc:  # the watchdog keeps trying
            self._record_failure(exc)
        if self._watchdog is None:
            self._watchdog = spawn(self._watch(), name="model-proxy-watchdog")

    async def refresh(self) -> None:
        """Push the current state. Safe to call often: callers that arrive while
        a push is in flight share the next one."""
        self._dirty = True
        async with self._lock:
            if not self._dirty:
                return
            self._dirty = False
            info = self._info
            if info is None:
                if self._idle:
                    self._retry_at = 0.0  # something changed: ask again at the next tick
                return
            state, self._prefetched = self._prefetched or await self._state_provider(), None
            try:
                r = await self._http.put(
                    self._url(info, "/_coffer/state"),
                    headers=self._auth(info),
                    content=state.model_dump_json(),
                )
                r.raise_for_status()
            except httpx.HTTPError as exc:
                self._last_error = f"state push failed: {type(exc).__name__}"
                _logger.warning("model_proxy.state_push_failed: %s", type(exc).__name__)
                return
            self._pushed_revision = state.revision
            if self._health is not None:
                self._health = {**self._health, "revision": state.revision}

    async def stop(self) -> None:
        """Stop supervising. The proxy keeps serving — it survives daemon restarts."""
        if self._watchdog is not None:
            self._watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog
            self._watchdog = None
        await self._http.aclose()

    def status(self) -> ProxyStatus:
        health = self._health or {}
        info = self._info
        return ProxyStatus(
            running=self._health is not None,
            pid=info.pid if info else None,
            port=self.port,
            version=health.get("version") if self._health else None,
            restarts=self._restarts,
            last_error=self._last_error,
            revision=health.get("revision") if self._health else None,
            started_at=health.get("started_at") if self._health else None,
            consecutive_failures=self._failures,
            failing=self._failures >= FAILING_AFTER,
        )

    # --- attach / spawn ------------------------------------------------------------------

    def _url(self, info: ProxyInfo, path: str) -> str:
        return f"http://127.0.0.1:{info.port}{path}"

    def _auth(self, info: ProxyInfo) -> dict[str, str]:
        return {CONTROL_TOKEN_HEADER: info.control_token}

    def _alive(self, pid: int) -> bool:
        if self._proc is not None and self._proc.pid == pid:
            return self._proc.poll() is None  # our own child: reap, don't see a zombie
        return _pid_alive(pid)

    async def _probe(self, info: ProxyInfo) -> dict[str, Any] | None:
        if not self._alive(info.pid):
            return None
        try:
            r = await self._http.get(self._url(info, "/_coffer/health"), headers=self._auth(info))
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        payload = r.json()
        return payload if isinstance(payload, dict) else None

    async def _attach_or_spawn(self) -> bool:
        """Attach to a live proxy of this build, or spawn one. ``False`` when
        there is none and none is needed: no agent is routed through the proxy,
        so starting a process for it would only be a process nothing talks to."""
        info = read_info(self.coffer_dir)
        if info is not None:
            health = await self._probe(info)
            if (
                health is not None
                and health.get("version") == self.version
                and info.port == self.port
            ):
                self._info, self._health = info, health
                _logger.info("model_proxy.attached pid=%s port=%s", info.pid, info.port)
                return True
            if health is not None:
                await self._replace(info, health)
        wanted = await self._state_provider()
        if not wanted.routes:
            return False
        self._prefetched = wanted  # the push that follows the spawn sends this one
        await self._spawn()
        return True

    async def _replace(self, info: ProxyInfo, health: dict[str, Any]) -> None:
        """Drain an old build's proxy and wait (bounded) for it to exit."""
        _logger.info(
            "model_proxy.replacing pid=%s version=%s -> %s",
            info.pid,
            health.get("version"),
            self.version,
        )
        with contextlib.suppress(httpx.HTTPError):
            await self._http.post(self._url(info, "/_coffer/drain"), headers=self._auth(info))
        deadline = time.monotonic() + self._drain_timeout
        while self._alive(info.pid) and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if self._alive(info.pid):
            raise RuntimeError(f"old model proxy pid {info.pid} did not finish draining")

    def _spawn_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self._env is not None:
            env.update(self._env)
        if self._command is None and not getattr(sys, "frozen", False):
            existing = env.get("PYTHONPATH")
            root = _source_root()
            env["PYTHONPATH"] = root + (os.pathsep + existing if existing else "")
        return env

    async def _spawn(self) -> None:
        command = self._command or default_proxy_command(self.port)
        log_path = log_dir() / "proxy.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as log:
            proc: subprocess.Popen[bytes] = subprocess.Popen(  # type: ignore[call-overload]
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env=self._spawn_env(),
                **detached_popen_kwargs(),
            )
        self._proc = proc
        deadline = time.monotonic() + self._spawn_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                if proc.returncode == EXIT_PORT_IN_USE:
                    raise RuntimeError(
                        f"model proxy could not bind 127.0.0.1:{self.port}: another process "
                        "holds the port and it is not the proxy this daemon supervises "
                        f"(see {log_path})"
                    )
                raise RuntimeError(f"model proxy exited at start (code {proc.returncode})")
            info = read_info(self.coffer_dir)
            if info is not None and info.pid == proc.pid:
                health = await self._probe(info)
                if health is not None:
                    self._info, self._health = info, health
                    self._pushed_revision = None
                    _logger.info("model_proxy.spawned pid=%s port=%s", proc.pid, info.port)
                    return
            await asyncio.sleep(0.05)
        raise RuntimeError("model proxy did not come up in time")

    # --- watchdog ---------------------------------------------------------------------

    def _go_idle(self) -> None:
        self._idle = True
        self._failures = 0
        self._retry_at = self._clock() + _IDLE_RECHECK

    def _record_failure(self, exc: Exception) -> None:
        """Count a failed start and push the next attempt out, doubling the wait
        up to the cap. Said once when it begins and once when it turns into a
        standing failure; after that the status carries it, the log does not."""
        message = f"{type(exc).__name__}: {exc}"
        changed = message != self._last_error
        self._last_error = message
        self._failures += 1
        delay = min(_BACKOFF_BASE * 2 ** (self._failures - 1), _BACKOFF_MAX)
        self._retry_at = self._clock() + delay
        if self._failures == 1 or self._failures == FAILING_AFTER or changed:
            _logger.warning(
                "model_proxy.restart_failed: %s (attempt %d, next in %.0fs)",
                message,
                self._failures,
                delay,
            )

    async def _tick(self) -> None:
        """One watchdog step: probe, and when the proxy is gone and the backoff
        has run out, attach or spawn it again."""
        info = self._info
        health = await self._probe(info) if info is not None else None
        if health is not None:
            self._health, self._failures, self._idle = health, 0, False
            if health.get("revision") != self._pushed_revision:
                await self.refresh()
            return
        self._health = None
        if self._clock() < self._retry_at:
            return
        try:
            attached = await self._attach_or_spawn()
        except Exception as exc:
            self._record_failure(exc)
            return
        if not attached:
            self._go_idle()
            return
        self._failures, self._idle = 0, False
        # Fed before it is counted: a status that says "restarted" then
        # describes a proxy that already holds the current state.
        await self.refresh()
        self._restarts += 1
        _logger.warning("model_proxy.restarted count=%s", self._restarts)

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._tick()


__all__ = ["ProxyStatus", "ProxySupervisor", "default_proxy_command"]
