"""Cursor, driven through ``cursor-agent -p --output-format stream-json`` (spec
chat "Run a turn through the agent's one-shot command").

One process per turn, the message as its argument and stdin closed.
``--force`` lets the agent run its commands without asking and ``--trust``
accepts the turn's folder, which print mode would otherwise refuse until a
person trusted it in the editor; together they are the agent's full
permissions, as Claude Code and Codex get. Cursor signs in with its own
account (``cursor-agent login`` or ``CURSOR_API_KEY``): it takes no custom
model endpoint, so a Coffer provider never serves it.

Cursor has no flag for an added system prompt, so the turn's system context
leads the message, fenced so the agent reads it as Coffer's note rather than
the person's words.

Lines (Cursor's documented ``stream-json``): ``system``/``init`` with the
session id and model, ``assistant`` per finished message, ``tool_call``
``started``/``completed`` keyed by a ``<kind>ToolCall`` object (or
``function``), and ``result`` at the end. A failure ends the process non-zero
with the reason on stderr and no ``result``.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from coffer.domain.chat.events import AgentEvent, TurnProgress
from coffer.infrastructure.chat.cli_turn import CliState, TurnPlan, obj

CONTEXT_OPEN = "<coffer-context>"
CONTEXT_CLOSE = "</coffer-context>"


def with_context(prompt: str, system_context: str) -> str:
    if not system_context.strip():
        return prompt
    return f"{CONTEXT_OPEN}\n{system_context.strip()}\n{CONTEXT_CLOSE}\n\n{prompt}"


class CursorPrint:
    agent_key = "cursor"
    process_name = "cursor-agent"

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
        argv = [binary, "-p", "--output-format", "stream-json", "--force", "--trust"]
        if resume:
            argv += ["--resume", resume]
        if model:
            argv += ["--model", model]
        argv += ["--", with_context(prompt, system_context)]
        return TurnPlan(argv=argv)

    def mapper(self) -> CursorMapper:
        return CursorMapper()


def _tool_parts(tool_call: object) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """``(name, args, result)`` of a ``tool_call`` object: one key naming the
    kind (``readToolCall`` → ``read``), or ``function`` with a name and JSON
    arguments."""
    if not isinstance(tool_call, dict) or not tool_call:
        return "tool", {}, None
    if isinstance(tool_call.get("function"), dict):
        fn = tool_call["function"]
        raw = fn.get("arguments")
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            args = {"arguments": raw}
        result = fn.get("result")
        return (
            str(fn.get("name") or "tool"),
            args if isinstance(args, dict) else {"arguments": args},
            result if isinstance(result, dict) else None,
        )
    key, body = next(iter(tool_call.items()))
    name = key[: -len("ToolCall")] if key.endswith("ToolCall") and len(key) > 8 else key
    body = obj(body)
    args = obj(body.get("args"))
    result = body.get("result") if isinstance(body.get("result"), dict) else None
    return name, args, result


def _result_error(result: dict[str, Any]) -> str | None:
    if "success" in result:
        return None
    for key in ("error", "failure", "rejected"):
        value = result.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            for field in ("error", "message", "reason"):
                if isinstance(value.get(field), str):
                    return str(value[field])
        return str(value)
    return None


class CursorMapper:
    def map(self, event: dict[str, Any], state: CliState) -> list[AgentEvent]:
        session = event.get("session_id")
        if isinstance(session, str) and session:
            state.session_id = session
        kind = event.get("type")
        if kind == "system":
            if isinstance(event.get("model"), str) and event["model"]:
                state.model = event["model"]
            return [TurnProgress()]
        if kind == "assistant":
            message = obj(event.get("message"))
            content = message.get("content")
            blocks = content if isinstance(content, list) else []
            text = "".join(
                str(b.get("text") or "")
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            )
            return state.text(text)
        if kind == "tool_call":
            call_id = str(event.get("call_id") or "")
            name, args, result = _tool_parts(event.get("tool_call"))
            if event.get("subtype") == "started":
                return [state.tool_call(call_id, name, args)]
            if event.get("subtype") == "completed":
                if call_id not in state.tool_names:
                    state.tool_call(call_id, name, args)
                error = _result_error(result) if result is not None else None
                output = (result or {}).get("success", result)
                return [state.tool_result(call_id, output, error)]
            return [TurnProgress()]
        if kind == "result":
            usage = obj(event.get("usage"))
            state.add_tokens(usage.get("inputTokens"), usage.get("outputTokens"))
            if event.get("is_error") or event.get("subtype") not in (None, "success"):
                return [state.error("cursor_error", str(event.get("result") or "Cursor failed"))]
            return [state.done()]
        return [TurnProgress()]


__all__ = ["CursorMapper", "CursorPrint", "with_context"]
