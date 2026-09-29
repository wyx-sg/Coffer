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

from coffer.domain.model_proxy.state import CONTROL_TOKEN_HEADER, ProxyState
from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.model_proxy.info import ProxyInfo, read_info
from coffer.infrastructure.platform.process import detached_popen_kwargs

_logger = logging.getLogger(__name__)

SPAWN_TIMEOUT_SECONDS = 20.0
DRAIN_TIMEOUT_SECONDS = 30.0
_HTTP_TIMEOUT = httpx.Timeout(5.0, connect=2.0)
_BACKOFF_MAX = 60.0


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
    ) -> None:
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
        self._http = httpx.AsyncClient(timeout=_HTTP_TIMEOUT, trust_env=False)

    # --- public ---------------------------------------------------------------------

    async def start(self) -> None:
        """Attach to a live same-version proxy, or replace/spawn one; push state;
        start the watchdog. May wait up to ``drain_timeout`` for an old build's
        proxy to finish its streams — run it in a background task if that matters."""
        try:
            await self._attach_or_spawn()
            await self.refresh()
        except Exception as exc:  # the watchdog keeps trying
            self._last_error = f"{type(exc).__name__}: {exc}"
            _logger.warning("model_proxy.supervisor_start_failed: %s", self._last_error)
        if self._watchdog is None:
            self._watchdog = asyncio.create_task(self._watch(), name="model-proxy-watchdog")

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
                return
            state = await self._state_provider()
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

    async def _attach_or_spawn(self) -> None:
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
                return
            if health is not None:
                await self._replace(info, health)
        await self._spawn()

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

    async def _watch(self) -> None:
        backoff = 1.0
        while True:
            await asyncio.sleep(self._interval)
            info = self._info
            health = await self._probe(info) if info is not None else None
            if health is not None:
                self._health, backoff = health, 1.0
                if health.get("revision") != self._pushed_revision:
                    await self.refresh()
                continue
            self._health = None
            try:
                await self._attach_or_spawn()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                _logger.warning("model_proxy.restart_failed: %s", self._last_error)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
                continue
            # Fed before it is counted: a status that says "restarted" then
            # describes a proxy that already holds the current state.
            await self.refresh()
            self._restarts += 1
            _logger.warning("model_proxy.restarted count=%s", self._restarts)


__all__ = ["ProxyStatus", "ProxySupervisor", "default_proxy_command"]
