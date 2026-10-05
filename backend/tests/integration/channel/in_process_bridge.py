"""The bridge's real session code, run on a thread instead of in a subprocess.

``SeaTalkWebSocketConnector`` talks to ``coffer-seatalk-bridge`` through a
``BridgeLink``. In production that is a subprocess; here it is the very same
``seatalk_bridge.session`` code — dispatcher wiring, handlers, ``ended``
reporting — driven against the in-memory fake SDK on a thread we own, with the
protocol lines round-tripped through JSON exactly as they would cross a pipe.
So the connector tests keep pinning real threads against a real event loop,
without spawning an interpreter per test. The subprocess itself is covered by
``test_seatalk_bridge_process.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from types import ModuleType
from typing import Any

from coffer.infrastructure.channel.seatalk_bridge.protocol import (
    SDK_PACKAGE,
    BridgeConfig,
    Emitter,
)
from coffer.infrastructure.channel.seatalk_bridge.session import Session, open_session
from coffer.infrastructure.channel.seatalk_bridge_process import BridgeLauncher, BridgeLink

_JOIN_TIMEOUT_SECONDS = 2.0


class InProcessBridge:
    """A ``BridgeLink`` whose bridge is a thread in this process."""

    def __init__(self, module: ModuleType | None, config: BridgeConfig) -> None:
        self._module = module
        self._config = config
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self._lock = threading.Lock()
        self._session: Session | None = None
        self._closed = False
        self.thread = threading.Thread(target=self._run, name="seatalk-bridge-test", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _load(self) -> ModuleType:
        if self._module is None:
            raise ModuleNotFoundError(f"No module named {SDK_PACKAGE!r}", name=SDK_PACKAGE)
        return self._module

    def _post(self, item: dict[str, Any] | None) -> None:
        with contextlib.suppress(RuntimeError):  # the loop is gone; so is the test
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def _write(self, line: bytes) -> None:
        self._post(json.loads(line))

    def _run(self) -> None:
        try:
            emitter = Emitter(self._write, secret=self._config.app_secret)
            session = open_session(self._load, self._config, emitter)
            if session is None:
                return
            with self._lock:
                self._session = session
                closed = self._closed
            if closed:
                session.close()
            session.run()
        finally:
            self._post(None)

    async def receive(self) -> dict[str, Any] | None:
        return await self._queue.get()

    async def close(self) -> None:
        with self._lock:
            self._closed = True
            session = self._session
        if session is not None:
            session.close()
        if self.thread.is_alive():
            await asyncio.to_thread(self.thread.join, _JOIN_TIMEOUT_SECONDS)

    def exit_detail(self) -> str:
        return "in-process bridge"


def in_process_bridge(module: ModuleType | None) -> BridgeLauncher:
    """A launcher running the bridge session against ``module`` (None: no SDK)."""

    async def launch(config: BridgeConfig) -> BridgeLink:
        bridge = InProcessBridge(module, config)
        bridge.start()
        return bridge

    return launch
