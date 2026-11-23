"""OpenCode, driven through ``opencode run --format json`` (spec chat "Run a turn
through the agent's one-shot command").

One process per turn, the message as its argument and stdin closed (OpenCode
1.x reads a piped stdin as the message and waits on one left open). OpenCode
2.x runs ``run`` against a background service unless told ``--standalone``,
which keeps the turn inside the process Coffer started and can stop.

The turn's system context goes to OpenCode as one more ``instructions`` file
through ``OPENCODE_CONFIG_CONTENT``, which OpenCode merges over the user's own
config, so their instructions stay and Coffer's come on top. Both 1.x and 2.x
print the same lines: ``step_start``, ``text``, ``tool_use`` (once the tool
has finished), ``step_finish`` with the step's tokens, and ``error``.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
from typing import Any

from coffer.domain.chat.events import AgentEvent, TurnProgress
from coffer.infrastructure.chat.cli_turn import CliState, TurnPlan, obj

#: OpenCode's ``provider/model`` prefix of the provider Coffer projects
#: (``coffer.domain.provider.opencode_projection.OPENCODE_PROVIDER_ID``; the
#: chat kind may not import the provider kind, so it is restated here).
_COFFER_PROVIDER = "coffer"
_CONFIG_CONTENT_ENV = "OPENCODE_CONFIG_CONTENT"
_VERSION = re.compile(r"v?(\d+)\.")

#: binary path -> major version, read once per binary.
_majors: dict[str, int | None] = {}


async def opencode_major(binary: str) -> int | None:
    """The major version ``opencode --version`` prints, cached per binary."""
    if binary in _majors:
        return _majors[binary]
    major: int | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "--version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), 30)
        match = _VERSION.search(out.decode("utf-8", "replace"))
        major = int(match.group(1)) if match else None
    except (OSError, TimeoutError):
        major = None
    _majors[binary] = major
    return major


def opencode_model(model: str | None) -> str | None:
    """The ``--model`` value: OpenCode names a model ``provider/model``; a bare
    id is one of the connection's models, served by Coffer's provider."""
    if not model:
        return None
    return model if "/" in model else f"{_COFFER_PROVIDER}/{model}"


def config_content(existing: str | None, instructions_file: pathlib.Path) -> str:
    """``OPENCODE_CONFIG_CONTENT`` with Coffer's instructions file added to
    whatever the daemon's own environment already set there."""
    data: dict[str, Any] = {}
    if existing:
        try:
            parsed = json.loads(existing)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            data = parsed
    current = data.get("instructions")
    files = list(current) if isinstance(current, list) else []
    files.append(str(instructions_file))
    data["instructions"] = files
    return json.dumps(data)


class OpenCodeRun:
    agent_key = "opencode"
    process_name = "opencode-run"

    async def plan(
        self,
        *,
        binary: str,
        prompt: str,
        model: str | None,
        resume: str | None,
        system_context: str,
        scratch: pathlib.Path,
    ) -> TurnPlan:
        argv = [binary, "run", "--format", "json", "--auto"]
        if (await opencode_major(binary) or 0) >= 2:
            argv.append("--standalone")
        if resume:
            argv += ["--session", resume]
        chosen = opencode_model(model)
        if chosen:
            argv += ["--model", chosen]
        env: dict[str, str] = {}
        if system_context.strip():
            instructions = scratch / "coffer-context.md"
            instructions.write_text(system_context, encoding="utf-8")
            env[_CONFIG_CONTENT_ENV] = config_content(
                os.environ.get(_CONFIG_CONTENT_ENV), instructions
            )
        # ``--`` so a message that starts with a dash is never read as a flag.
        argv += ["--", prompt]
        return TurnPlan(argv=argv, env=env)

    def mapper(self) -> OpenCodeMapper:
        return OpenCodeMapper()


def _error_message(error: object) -> str:
    if isinstance(error, dict):
        data = error.get("data")
        if isinstance(data, dict) and isinstance(data.get("message"), str):
            return str(data["message"])
        if isinstance(error.get("message"), str):
            return str(error["message"])
        if isinstance(error.get("name"), str):
            return str(error["name"])
    return "OpenCode reported an error"


class OpenCodeMapper:
    def map(self, event: dict[str, Any], state: CliState) -> list[AgentEvent]:
        session = event.get("sessionID")
        if isinstance(session, str) and session:
            state.session_id = session
        part = obj(event.get("part"))
        kind = event.get("type")
        if kind == "text":
            return state.text(str(part.get("text") or ""))
        if kind == "tool_use":
            return self._tool(part, state)
        if kind == "step_finish":
            tokens = obj(part.get("tokens"))
            state.add_tokens(tokens.get("input"), tokens.get("output"))
            return [TurnProgress()]
        if kind == "error":
            return [state.error("opencode_error", _error_message(event.get("error")))]
        return [TurnProgress()]

    @staticmethod
    def _tool(part: dict[str, Any], state: CliState) -> list[AgentEvent]:
        # 1.x names the call ``callID`` (``id`` is the part's own); 2.x names
        # it ``id`` and the part ``partID``.
        call_id = str(part.get("callID") or part.get("id") or "")
        name = str(part.get("tool") or "tool")
        st = obj(part.get("state"))
        events: list[AgentEvent] = [state.tool_call(call_id, name, st.get("input") or {})]
        if st.get("status") == "error":
            events.append(state.tool_result(call_id, None, str(st.get("error") or "failed")))
        else:
            events.append(state.tool_result(call_id, {"output": st.get("output")}, None))
        return events


__all__ = ["OpenCodeMapper", "OpenCodeRun", "config_content", "opencode_major", "opencode_model"]
