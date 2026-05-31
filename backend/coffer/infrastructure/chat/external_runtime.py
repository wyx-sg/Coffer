"""ExternalAgentRuntime — drives a managed external agent's CLI headlessly.

Spawns ``claude`` / ``codex`` as a local subprocess in streaming mode and maps
its stdout to ``RuntimeEvent``s. No LangChain dependency. The binary is
resolved from an explicit env override (``COFFER_CHAT_BIN_<TYPE>``) or the
PATH; a missing binary surfaces as a structured error rather than a crash, and
the child is always reaped (no orphans on end / error / stop / shutdown).

Confirmation is not wired for external agents in v1 (their CLIs run under their
own permission policy); ``resolve_confirmation`` is therefore a no-op and the
chat service never gates external turns (``confirm_tools`` is empty for them).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from coffer.domain.chat.runtime import (
    ChatTurnRequest,
    DoneEvent,
    ErrorEvent,
    RuntimeEvent,
    TextDelta,
)

# Agent type -> (binary name, env var carrying its config dir).
_BINARY = {"claude_code": "claude", "codex": "codex"}
_CONFIG_DIR_ENV = {"claude_code": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME"}


def _resolve_binary(agent_type: str) -> str | None:
    override = os.environ.get(f"COFFER_CHAT_BIN_{agent_type.upper()}")
    if override:
        return override
    name = _BINARY.get(agent_type)
    return shutil.which(name) if name else None


def _command(agent_type: str, binary: str, prompt: str) -> list[str]:
    if agent_type == "claude_code":
        return [binary, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if agent_type == "codex":
        return [binary, "exec", "--json", prompt]
    return [binary, prompt]


def _text_from_line(line: str) -> list[RuntimeEvent]:
    """Map one stdout line of an agent CLI to runtime events.

    Handles a small, tolerant set of shapes: our stub/`{type:text}` events,
    Claude Code ``stream-json`` assistant blocks, and a plain-text fallback.
    Control/unknown JSON lines are ignored.
    """
    raw = line.strip()
    if not raw:
        return []
    try:
        obj: Any = json.loads(raw)
    except ValueError:
        return [TextDelta(text=raw)]
    if not isinstance(obj, dict):
        return []
    if isinstance(obj.get("text"), str):
        return [TextDelta(text=obj["text"])]
    if obj.get("type") == "assistant" and isinstance(obj.get("message"), dict):
        blocks = obj["message"].get("content", [])
        out: list[RuntimeEvent] = []
        if isinstance(blocks, list):
            for b in blocks:
                if (
                    isinstance(b, dict)
                    and b.get("type") == "text"
                    and isinstance(b.get("text"), str)
                ):
                    out.append(TextDelta(text=b["text"]))
        return out
    return []


class ExternalAgentRuntime:
    def __init__(self, *, config: dict[str, Any]) -> None:
        self._type = str(config.get("type", ""))
        self._config_dir = config.get("config_dir")
        self._proc: asyncio.subprocess.Process | None = None
        self._stopped = False

    async def stream(self, request: ChatTurnRequest) -> AsyncIterator[RuntimeEvent]:
        binary = _resolve_binary(self._type)
        if binary is None:
            yield ErrorEvent(
                code="UPSTREAM_UNAVAILABLE",
                message=f"agent binary for {self._type!r} not found on PATH",
            )
            return

        env = dict(os.environ)
        if self._config_dir and self._type in _CONFIG_DIR_ENV:
            env[_CONFIG_DIR_ENV[self._type]] = str(self._config_dir)

        argv = _command(self._type, binary, request.user_message)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except (OSError, ValueError) as e:
            yield ErrorEvent(code="UPSTREAM_UNAVAILABLE", message=f"failed to spawn {binary}: {e}")
            return

        proc = self._proc
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                if self._stopped:
                    break
                for ev in _text_from_line(raw.decode("utf-8", errors="replace")):
                    yield ev
            await proc.wait()
            if self._stopped:
                return
            if proc.returncode not in (0, None):
                stderr = b""
                if proc.stderr is not None:
                    stderr = await proc.stderr.read()
                yield ErrorEvent(
                    code="UPSTREAM_UNAVAILABLE",
                    message=(
                        f"{binary} exited with code {proc.returncode}: "
                        f"{stderr.decode('utf-8', errors='replace')[:200]}"
                    ),
                )
                return
            yield DoneEvent()
        finally:
            await self._terminate()

    async def _terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()

    async def resolve_confirmation(self, request_id: str, approve: bool) -> None:
        # External agents are not confirmation-gated in v1.
        return None

    async def stop(self) -> None:
        self._stopped = True
        await self._terminate()
