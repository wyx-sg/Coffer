"""Start ``coffer-seatalk-bridge`` and talk to it — the daemon's half of the bridge.

The SeaTalk SDK never enters the daemon (spec channels/seatalk "Load the
websocket client library from an operator-supplied directory"): each
connection attempt is one bridge process, which imports the SDK from the
vendor directory, holds the connection, and writes events back as JSON lines
(``seatalk_bridge.protocol``).

* **Which executable.** A frozen daemon runs the ``coffer-seatalk-bridge``
  sitting beside it — inside Coffer.app that is ``Contents/MacOS``, signed
  without the keychain entitlement and not re-signed by the bundle. Unfrozen
  (development, tests) it is ``python -m coffer.infrastructure.channel.seatalk_bridge``.
* **What it inherits.** An allow-listed environment: the path, home, locale,
  temp dir, proxy and CA settings the SDK's network calls need, and nothing
  named ``COFFER_*``. The app secret goes in on stdin only, never argv or env.
* **Its own session**, so a signal aimed at the daemon's process group does not
  take the bridge down mid-ack, and closing stdin is how the daemon stops it.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from coffer.infrastructure.channel.seatalk_bridge.protocol import (
    BridgeConfig,
    encode_config,
    scrub,
)

_logger = logging.getLogger(__name__)

BRIDGE_EXECUTABLE = "coffer-seatalk-bridge"
BRIDGE_MODULE = "coffer.infrastructure.channel.seatalk_bridge"
# One event envelope per line; a forwarded record can be large, so the limit is
# generous — but bounded, so a runaway writer cannot exhaust the daemon.
_LINE_LIMIT = 16 * 1024 * 1024
_STDERR_TAIL_LINES = 20
_CLOSE_TIMEOUT_SECONDS = 5.0
_KILL_TIMEOUT_SECONDS = 2.0

_PASSED_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TZ",
        "LANG",
        "LANGUAGE",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    }
)


class BridgeUnavailableError(RuntimeError):
    """The bridge executable is not where this build ships it."""


class BridgeLink(Protocol):
    """One running bridge, as the connector sees it."""

    async def receive(self) -> dict[str, Any] | None:
        """The next protocol message, or None once the bridge's output has ended."""
        ...

    async def close(self) -> None:
        """Stop the bridge (idempotent)."""
        ...

    def exit_detail(self) -> str:
        """How the bridge ended, for a report when it ended without saying."""
        ...


BridgeLauncher = Callable[[BridgeConfig], Awaitable[BridgeLink]]


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bridge_command(*, frozen: bool | None = None) -> list[str]:
    """The argv that starts the bridge — no secret in it, ever."""
    if frozen if frozen is not None else _frozen():
        executable = Path(sys.executable).resolve().parent / BRIDGE_EXECUTABLE
        if not executable.is_file():
            raise BridgeUnavailableError(
                f"{BRIDGE_EXECUTABLE} is missing beside {Path(sys.executable).resolve()}; "
                "this build cannot receive SeaTalk events — reinstall Coffer"
            )
        return [str(executable)]
    return [sys.executable, "-m", BRIDGE_MODULE]


def bridge_environment(
    source: Mapping[str, str] | None = None, *, frozen: bool | None = None
) -> dict[str, str]:
    """The allow-listed environment the bridge runs with."""
    env = os.environ if source is None else source
    out = {k: v for k, v in env.items() if k in _PASSED_NAMES or k.startswith("LC_")}
    if not (frozen if frozen is not None else _frozen()):
        # Development: the module must import from THIS checkout, not whatever
        # copy of coffer the interpreter's site-packages happens to hold.
        import coffer

        root = str(Path(coffer.__file__).resolve().parent.parent)
        inherited = env.get("PYTHONPATH")
        out["PYTHONPATH"] = os.pathsep.join([root, inherited] if inherited else [root])
    return out


class SubprocessBridge:
    """A ``coffer-seatalk-bridge`` process speaking the protocol on its pipes."""

    def __init__(self, process: asyncio.subprocess.Process, secret: str) -> None:
        self._process = process
        self._secret = secret
        self._stderr: collections.deque[str] = collections.deque(maxlen=_STDERR_TAIL_LINES)
        self._stderr_task = asyncio.ensure_future(self._drain_stderr())
        self._closing: asyncio.Future[None] | None = None

    @classmethod
    async def spawn(cls, config: BridgeConfig) -> SubprocessBridge:
        process = await asyncio.create_subprocess_exec(
            *bridge_command(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=bridge_environment(),
            start_new_session=True,
            limit=_LINE_LIMIT,
        )
        bridge = cls(process, config.app_secret)
        try:
            assert process.stdin is not None
            process.stdin.write(encode_config(config))
            await process.stdin.drain()
        except (OSError, ConnectionError):
            # It died before reading its config; receive() reports how.
            pass
        return bridge

    async def receive(self) -> dict[str, Any] | None:
        stdout = self._process.stdout
        assert stdout is not None
        while True:
            line = await stdout.readline()
            if not line:
                return None
            try:
                message = json.loads(line)
            except ValueError:
                _logger.warning(
                    "channel.seatalk_bridge.unreadable_line", extra={"bytes": len(line)}
                )
                continue
            if isinstance(message, dict):
                return message

    async def close(self) -> None:
        if self._closing is None:
            self._closing = asyncio.ensure_future(self._shutdown())
        await asyncio.shield(self._closing)

    async def _shutdown(self) -> None:
        process = self._process
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), _CLOSE_TIMEOUT_SECONDS)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), _KILL_TIMEOUT_SECONDS)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._stderr_task, 1.0)

    async def _drain_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:
            return
        with contextlib.suppress(Exception):
            while line := await stderr.readline():
                self._stderr.append(line.decode("utf-8", "replace").rstrip())

    def exit_detail(self) -> str:
        code = self._process.returncode
        status = "still running" if code is None else f"exit code {code}"
        tail = scrub(" | ".join(t for t in self._stderr if t), self._secret)
        return f"{status}: {tail}" if tail else status


async def spawn_bridge(config: BridgeConfig) -> BridgeLink:
    """The production ``BridgeLauncher``."""
    return await SubprocessBridge.spawn(config)


__all__ = [
    "BRIDGE_EXECUTABLE",
    "BridgeLauncher",
    "BridgeLink",
    "BridgeUnavailableError",
    "SubprocessBridge",
    "bridge_command",
    "bridge_environment",
    "spawn_bridge",
]
