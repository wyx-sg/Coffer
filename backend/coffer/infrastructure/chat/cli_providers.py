"""CLI-agent providers + dialects — Claude Code and Codex behind the chat seam.

Each provider implements ``AgentProvider``: ``init_conversation`` validates and
stores the working directory in ``agent_config``; ``build_adapter`` constructs a
``CliAgentAdapter`` wired to the product's :class:`CliDialect`; ``availability``
reports whether the CLI binary is on PATH.

The dialects encode each product's argv shape and line-delimited JSON output.
Both are verified against the real CLIs: the Claude Code stream-json schema and
the Codex ``exec --json`` schema (codex-cli 0.125.0) are each mapped from
captured output and pinned by fixtures in ``test_cli_agent.py``. Unrecognized
lines are ignored rather than failing the turn.
"""

from __future__ import annotations

import shutil
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.cli_agent import (
    CliAgentAdapter,
    ParseState,
    Spawner,
    default_spawner,
)


def _stringify(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in content]
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Dialects
# ---------------------------------------------------------------------------


class ClaudeCodeDialect:
    """Argv + stream-json parsing for ``claude -p --output-format stream-json``."""

    binary = "claude"

    def build_argv(
        self, prompt: str, *, resume_session: str | None, extra: dict[str, Any]
    ) -> list[str]:
        argv = [self.binary, "-p", prompt, "--output-format", "stream-json", "--verbose"]
        # Full permissions — Coffer does not gate individual tool calls; the owner
        # driving the conversation is the trust boundary.
        argv += ["--permission-mode", "bypassPermissions"]
        if resume_session:
            argv += ["--resume", resume_session]
        return argv

    def parse(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        kind = line.get("type")
        if kind == "system" and line.get("subtype") == "init":
            state.session_id = line.get("session_id") or state.session_id
            return []
        if kind == "assistant":
            state.session_id = line.get("session_id") or state.session_id
            return self._assistant_blocks(line.get("message") or {}, state)
        if kind == "user":
            return self._tool_results(line.get("message") or {}, state)
        if kind == "result":
            return self._result(line, state)
        return []

    def _assistant_blocks(self, message: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        out: list[AgentEvent] = []
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                out.append(TextDelta(text=str(block["text"])))
            elif block.get("type") == "tool_use":
                tid = str(block.get("id", ""))
                name = str(block.get("name", ""))
                state.tool_names[tid] = name
                out.append(
                    ToolCall(tool_use_id=tid, tool_name=name, tool_input=block.get("input") or {})
                )
        return out

    def _tool_results(self, message: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        out: list[AgentEvent] = []
        for block in message.get("content", []):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tid = str(block.get("tool_use_id", ""))
            content = block.get("content")
            is_error = bool(block.get("is_error"))
            out.append(
                ToolResult(
                    tool_use_id=tid,
                    tool_name=state.tool_names.get(tid, ""),
                    output=None if is_error else {"content": _stringify(content)},
                    error=_stringify(content) if is_error else None,
                )
            )
        return out

    def _result(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        state.session_id = line.get("session_id") or state.session_id
        usage = line.get("usage") or {}
        state.prompt_tokens = usage.get("input_tokens")
        state.completion_tokens = usage.get("output_tokens")
        state.terminal_emitted = True
        if line.get("is_error") or line.get("subtype") not in (None, "success"):
            return [
                TurnError(
                    code="cli_error",
                    message=str(line.get("result") or line.get("subtype") or "claude error"),
                )
            ]
        return [
            TurnDone(
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                stop_reason="end_turn",
            )
        ]


class CodexDialect:
    """Argv + ``codex exec --json`` parsing.

    Verified against codex-cli 0.125.0. The event stream is flat JSONL — there
    is no ``msg`` envelope — with these line types:

      ``{"type":"thread.started","thread_id":"<uuid>"}``   — the session id
      ``{"type":"turn.started"}``                          — ignored
      ``{"type":"item.started","item":{...}}``             — ignored (see below)
      ``{"type":"item.completed","item":{...}}``           — text / tool content
      ``{"type":"turn.completed","usage":{...}}``          — terminal success
      ``{"type":"error","message":"..."}`` and
      ``{"type":"turn.failed","error":{"message":"..."}}`` — terminal failure

    Content is carried ONLY on ``item.completed`` — ``item.started`` repeats the
    same item id with partial data — so we map completions and ignore starts;
    that is the de-dup that stops a tool call or message from being emitted
    twice. A ``command_execution`` / ``file_change`` completion carries both the
    call AND its result (exit code + output / the changed paths), so each maps
    to a ``ToolCall`` followed by a ``ToolResult``.

    Resume uses the ``codex exec resume <session_id>`` subcommand, which replays
    ``thread.started`` with the SAME ``thread_id`` so the session id stays
    stable across turns.
    """

    binary = "codex"

    def build_argv(
        self, prompt: str, *, resume_session: str | None, extra: dict[str, Any]
    ) -> list[str]:
        if resume_session:
            return [self.binary, "exec", "resume", resume_session, "--json", prompt]
        return [self.binary, "exec", "--json", prompt]

    def parse(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        kind = line.get("type")
        if kind == "thread.started":
            thread = line.get("thread_id")
            if thread:
                state.session_id = str(thread)
            return []
        if kind == "item.completed":
            return self._item(line.get("item") or {}, state)
        if kind == "turn.completed":
            return self._complete(line, state)
        if kind in ("error", "turn.failed"):
            return self._error(line, state)
        return []

    def _item(self, item: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        itype = item.get("type")
        if itype == "agent_message":
            text = item.get("text")
            return [TextDelta(text=str(text))] if text else []
        if itype == "command_execution":
            return self._command(item, state)
        if itype == "file_change":
            return self._file_change(item, state)
        return []

    def _command(self, item: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        tid = str(item.get("id", ""))
        command = str(item.get("command", ""))
        state.tool_names[tid] = "shell"
        call = ToolCall(tool_use_id=tid, tool_name="shell", tool_input={"command": command})
        exit_code = item.get("exit_code")
        output = str(item.get("aggregated_output", ""))
        if exit_code not in (0, None):
            result = ToolResult(
                tool_use_id=tid,
                tool_name="shell",
                output=None,
                error=output or f"command exited with code {exit_code}",
            )
        else:
            result = ToolResult(
                tool_use_id=tid,
                tool_name="shell",
                output={"output": output, "exit_code": exit_code},
                error=None,
            )
        return [call, result]

    def _file_change(self, item: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        tid = str(item.get("id", ""))
        changes = item.get("changes") or []
        state.tool_names[tid] = "file_change"
        return [
            ToolCall(tool_use_id=tid, tool_name="file_change", tool_input={"changes": changes}),
            ToolResult(
                tool_use_id=tid, tool_name="file_change", output={"changes": changes}, error=None
            ),
        ]

    def _complete(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        usage = line.get("usage") or {}
        state.prompt_tokens = usage.get("input_tokens")
        state.completion_tokens = usage.get("output_tokens")
        state.terminal_emitted = True
        return [
            TurnDone(
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                stop_reason="end_turn",
            )
        ]

    def _error(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        # codex emits BOTH an `error` and a `turn.failed` for one failure; emit
        # a single TurnError. `error` carries a top-level `message`; `turn.failed`
        # nests it under `error.message`.
        if state.terminal_emitted:
            return []
        state.terminal_emitted = True
        message = line.get("message")
        if message is None:
            nested = line.get("error")
            if isinstance(nested, dict):
                message = nested.get("message")
        return [TurnError(code="cli_error", message=str(message or "codex error"))]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class _CliAgentProvider:
    """Shared ``AgentProvider`` body for CLI-backed agents."""

    def __init__(
        self,
        *,
        agent_key: str,
        dialect: Any,
        conversations: ConversationRepo,
        spawn: Spawner | None = None,
        which: Any = shutil.which,
    ) -> None:
        self.agent_key = agent_key
        self._dialect = dialect
        self._conversations = conversations
        self._spawn = spawn or default_spawner
        self._which = which

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        cwd = agent_config.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            raise AgentConfigRejected(
                reason="invalid_cwd",
                message="agent_config.cwd (a working directory path) is required",
            )
        import pathlib

        if not pathlib.Path(cwd).expanduser().is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
        stored: dict[str, Any] = {"cwd": str(pathlib.Path(cwd).expanduser())}
        await self._conversations.set_agent_config(conversation_id, stored)

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        config = await self._conversations.get_agent_config(conversation_id)
        cwd = config.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            raise AgentConfigRejected(
                reason="invalid_cwd",
                message="conversation has no working directory configured",
            )

        async def _save_session(session_id: str) -> None:
            latest = await self._conversations.get_agent_config(conversation_id)
            latest["session_id"] = session_id
            await self._conversations.set_agent_config(conversation_id, latest)

        return CliAgentAdapter(
            dialect=self._dialect,
            cwd=cwd,
            resume_session=config.get("session_id"),
            extra=config,
            spawn=self._spawn,
            on_session=_save_session,
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        return self._which(self._dialect.binary) is not None


class ClaudeCodeProvider(_CliAgentProvider):
    """``AgentProvider`` for the Claude Code CLI."""

    def __init__(self, *, conversations: ConversationRepo, spawn: Spawner | None = None, **kw: Any):
        super().__init__(
            agent_key="claude_code",
            dialect=ClaudeCodeDialect(),
            conversations=conversations,
            spawn=spawn,
            **kw,
        )


class CodexProvider(_CliAgentProvider):
    """``AgentProvider`` for the Codex CLI."""

    def __init__(self, *, conversations: ConversationRepo, spawn: Spawner | None = None, **kw: Any):
        super().__init__(
            agent_key="codex",
            dialect=CodexDialect(),
            conversations=conversations,
            spawn=spawn,
            **kw,
        )


__all__ = [
    "ClaudeCodeDialect",
    "ClaudeCodeProvider",
    "CodexDialect",
    "CodexProvider",
]
