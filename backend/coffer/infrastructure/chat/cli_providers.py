"""CLI-agent providers + dialects — Claude Code and Codex behind the chat seam.

Each provider implements ``AgentProvider``: ``init_conversation`` validates and
stores the working directory in ``agent_config``; ``build_adapter`` constructs a
``CliAgentAdapter`` wired to the product's :class:`CliDialect`; ``availability``
reports whether the CLI binary is on PATH.

The dialects encode each product's argv shape and line-delimited JSON output.
The Claude Code stream-json schema is stable and fully mapped. The Codex
``exec --json`` schema is mapped on a best-effort basis and is pending
real-CLI verification; unrecognized lines are ignored rather than failing the
turn, and tests pin the assumed shapes.
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
        argv += ["--permission-mode", str(extra.get("permission_mode") or "default")]
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
    """Argv + ``codex exec --json`` parsing (best-effort; pending verification)."""

    binary = "codex"

    def build_argv(
        self, prompt: str, *, resume_session: str | None, extra: dict[str, Any]
    ) -> list[str]:
        if resume_session:
            return [self.binary, "exec", "resume", resume_session, "--json", prompt]
        return [self.binary, "exec", "--json", prompt]

    def parse(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        # Codex nests its payload under "msg" (older) or emits flat "item"/"type"
        # events (newer). Handle both shapes; ignore anything unrecognized.
        inner = line.get("msg")
        msg: dict[str, Any] = inner if isinstance(inner, dict) else line
        kind = msg.get("type")
        thread = line.get("thread_id") or msg.get("thread_id") or msg.get("session_id")
        if thread:
            state.session_id = str(thread)
        if kind in ("agent_message", "agent_message_delta"):
            text = msg.get("message") or msg.get("text") or msg.get("delta") or ""
            return [TextDelta(text=str(text))] if text else []
        if kind == "item.completed":
            # Only the terminal item.completed carries content; emitting on
            # item.started too would duplicate every text block and tool call.
            return self._item(msg.get("item") or {}, state)
        if kind in ("turn.completed", "task_complete", "turn_complete"):
            return self._complete(msg, state)
        if kind in ("error", "turn.failed"):
            state.terminal_emitted = True
            return [TurnError(code="cli_error", message=str(msg.get("message") or "codex error"))]
        return []

    def _item(self, item: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        itype = item.get("type")
        if itype == "agent_message" and item.get("text"):
            return [TextDelta(text=str(item["text"]))]
        if itype in ("command_execution", "tool_call", "function_call"):
            tid = str(item.get("id", item.get("call_id", "")))
            name = str(item.get("name") or item.get("command") or "command")
            state.tool_names[tid] = name
            return [ToolCall(tool_use_id=tid, tool_name=name, tool_input=item.get("input") or {})]
        return []

    def _complete(self, msg: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        usage = msg.get("usage") or {}
        state.prompt_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
        state.completion_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
        state.terminal_emitted = True
        return [
            TurnDone(
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                stop_reason="end_turn",
            )
        ]


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
        if isinstance(agent_config.get("permission_mode"), str):
            stored["permission_mode"] = agent_config["permission_mode"]
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
