"""DeepSeek Harness, driven through ``dsh --profile headless --json`` (spec chat
"Run a turn through the agent's one-shot command").

One process per turn. The message goes on stdin (``-``), so its length and its
first character never matter to the command line. ``--permission-mode
danger-full-access --approval-policy never`` gives the turn the agent's full
permissions, as Claude Code and Codex get; headless has no channel to ask on.

DeepSeek Harness has no flag for the model or for an added system prompt; both
go in a ``--patch`` overlay written for the turn: ``agent-default-model``
(``provider`` + ``model``) and ``system-prompt.personaSuffix``, the template
DeepSeek Harness places after its own guidance. The overlay is JSON, which
YAML reads as-is. Lines: ``session`` first, ``status`` while it works,
``text``/``thinking`` per committed message, ``tool_call``/``tool_result``,
then ``final`` with the turn's reason, or ``error`` outside a turn.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from coffer.domain.chat.events import AgentEvent, TurnProgress
from coffer.infrastructure.chat.cli_turn import CliState, TurnPlan, obj

#: The provider route Coffer projects into DeepSeek Harness; a bare model id
#: is one of its models.
_COFFER_ROUTE = "coffer"


def dsh_model(model: str) -> tuple[str, str]:
    """``(provider, model)`` for ``agent-default-model``: ``route/model`` names
    the route; a bare id is a model of Coffer's route."""
    route, sep, rest = model.partition("/")
    return (route, rest) if sep and route and rest else (_COFFER_ROUTE, model)


def _template_safe(text: str) -> str:
    # personaSuffix is a ``{{…}}`` template; a literal pair in the context must
    # not be read as a placeholder.
    return text.replace("{{", "{ {").replace("}}", "} }")


def turn_patch(*, system_context: str, model: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if system_context.strip():
        rows.append(
            {"id": "system-prompt", "config": {"personaSuffix": _template_safe(system_context)}}
        )
    if model:
        route, model_id = dsh_model(model)
        rows.append({"id": "agent-default-model", "config": {"provider": route, "model": model_id}})
    return rows


class DshHeadless:
    agent_key = "deepseek_harness"
    process_name = "dsh-headless"

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
        argv = [binary, "--profile", "headless"]
        rows = turn_patch(system_context=system_context, model=model)
        if rows:
            patch = scratch / "coffer-turn.patch.yml"
            patch.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            argv += ["--patch", str(patch)]
        argv += [
            "--json",
            "--permission-mode",
            "danger-full-access",
            "--approval-policy",
            "never",
        ]
        if resume:
            argv += ["--session-id", resume]
        argv.append("-")
        return TurnPlan(argv=argv, stdin=prompt)

    def mapper(self) -> DshMapper:
        return DshMapper()


def _reason_error(reason: dict[str, Any]) -> tuple[str, str]:
    error = obj(reason.get("error"))
    code = str(error.get("code") or "dsh_error")
    message = str(error.get("message") or "DeepSeek Harness ended the turn with an error")
    return code, message


class DshMapper:
    def map(self, event: dict[str, Any], state: CliState) -> list[AgentEvent]:
        kind = event.get("type")
        session = event.get("sessionId")
        if isinstance(session, str) and session:
            state.session_id = session
        if kind == "text":
            return state.text(str(event.get("text") or ""))
        if kind == "tool_call":
            call_id = str(event.get("callId") or "")
            return [state.tool_call(call_id, str(event.get("tool") or "tool"), event.get("input"))]
        if kind == "tool_result":
            call_id = str(event.get("callId") or "")
            if event.get("status") == "error":
                return [state.tool_result(call_id, None, str(event.get("result") or "failed"))]
            return [state.tool_result(call_id, {"output": event.get("result")}, None)]
        if kind == "status" and event.get("phase") == "step_end":
            usage = obj(event.get("usage"))
            state.add_tokens(usage.get("inputTokens"), usage.get("outputTokens"))
            return [TurnProgress()]
        if kind == "final":
            reason = obj(event.get("reason"))
            outcome = reason.get("kind")
            if outcome == "completed":
                return [state.done()]
            if outcome == "error":
                return [state.error(*_reason_error(reason))]
            if outcome == "aborted":
                return [state.error("dsh_aborted", "DeepSeek Harness stopped the turn")]
            return [state.error("dsh_unfinished", "DeepSeek Harness ended without finishing")]
        if kind == "error":
            return [
                state.error("dsh_error", str(event.get("message") or "DeepSeek Harness failed"))
            ]
        return [TurnProgress()]


__all__ = ["DshHeadless", "DshMapper", "dsh_model", "turn_patch"]
