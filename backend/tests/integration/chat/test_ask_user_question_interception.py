"""Claude Code's own ``AskUserQuestion`` becomes a Coffer question (spec chat
"Pause a turn on a question for the owner").

The adapter registers a ``can_use_tool`` callback: the CLI consults it for a tool
that requires user interaction even under ``bypassPermissions`` (verified against
the bundled CLI, see the change's design §3). The callback is called directly
here with the input the CLI would send, since no real ``claude`` runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from coffer.application.chat import questions
from coffer.application.chat.question_agents import asker_for
from coffer.application.chat.questions import AnswerInput
from coffer.infrastructure.chat.claude_sdk_agent import ClaudeSdkAgentAdapter

pytestmark = pytest.mark.asyncio

_CTX = ToolPermissionContext(tool_use_id="toolu_1")

#: What Claude Code sends for ``AskUserQuestion`` (``multiSelect``, no ``context``).
_INPUT: dict[str, Any] = {
    "questions": [
        {
            "header": "Apply",
            "question": "Apply this change to staging?",
            "multiSelect": False,
            "options": [
                {"label": "Yes", "description": "Roll it out"},
                {"label": "No", "description": "Keep it local"},
            ],
        },
        {
            "header": "Parts",
            "question": "Which parts?",
            "multiSelect": True,
            "options": [{"label": "api", "description": "x"}, {"label": "web", "description": "y"}],
        },
    ]
}


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    questions.clear_all()
    yield
    questions.clear_all()


def _adapter(conversation_id: str) -> ClaudeSdkAgentAdapter:
    async def _noop(_session_id: str) -> None:
        return None

    return ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=None,
        extra={},
        session_factory=lambda _options: None,  # type: ignore[arg-type,return-value]
        on_session=_noop,
        ask_owner=asker_for(conversation_id),
    )


async def _pending(conversation_id: str) -> Any:
    for _ in range(200):
        block = questions.pending_question_for(conversation_id)
        if block is not None:
            return block
        await asyncio.sleep(0.005)
    raise AssertionError("no question raised")


@pytest.mark.acceptance(
    spec="chat", scenario="AskUserQuestion waits for the owner and gets the answer"
)
async def test_ask_user_question_waits_and_hands_the_answers_back_as_the_tools_own() -> None:
    ctx = questions.register_turn("conv")
    adapter = _adapter("conv")
    call = asyncio.create_task(adapter._can_use_tool("AskUserQuestion", _INPUT, _CTX))

    block = await _pending("conv")
    await asyncio.sleep(0.05)
    assert not call.done(), "the tool must wait for the owner"
    assert block.questions[1].multi_select is True and block.questions[0].options[0].description

    await questions.answer_question(
        "conv", block.question_id, [AnswerInput(selected=["Yes"])], via="web", by="ui"
    )
    await questions.answer_question(
        "conv", block.question_id, [AnswerInput(selected=["api", "web"])], via="web", by="ui"
    )
    result = await asyncio.wait_for(call, 2.0)

    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input is not None
    # The tool's own `answers`: question text -> answer, several labels joined.
    assert result.updated_input["answers"] == {
        "Apply this change to staging?": "Yes",
        "Which parts?": "api, web",
    }
    assert result.updated_input["questions"] == _INPUT["questions"]
    questions.release_turn(ctx)


async def test_a_cancelled_question_denies_the_tool_with_the_reason() -> None:
    ctx = questions.register_turn("conv")
    adapter = _adapter("conv")
    call = asyncio.create_task(adapter._can_use_tool("AskUserQuestion", _INPUT, _CTX))
    await _pending("conv")

    await questions.close_turn(ctx)
    result = await asyncio.wait_for(call, 2.0)

    assert isinstance(result, PermissionResultDeny)
    assert result.message == "The owner stopped the task."


async def test_a_malformed_ask_denies_the_tool_with_what_is_wrong() -> None:
    ctx = questions.register_turn("conv")
    result = await _adapter("conv")._can_use_tool("AskUserQuestion", {"questions": []}, _CTX)
    assert isinstance(result, PermissionResultDeny) and "1 to 4 questions" in result.message
    questions.release_turn(ctx)


async def test_every_other_tool_is_allowed_untouched() -> None:
    ctx = questions.register_turn("conv")
    result = await _adapter("conv")._can_use_tool("Bash", {"command": "ls"}, _CTX)
    assert isinstance(result, PermissionResultAllow) and result.updated_input is None
    questions.release_turn(ctx)


async def test_the_callback_is_registered_only_inside_a_turn_coffer_runs() -> None:
    ctx = questions.register_turn("conv")
    inside = _adapter("conv")._build_options(resume=None)
    assert inside.can_use_tool is not None
    # Coffer still does not gate tool calls: the agent keeps its full permissions.
    assert inside.permission_mode == "bypassPermissions"
    questions.release_turn(ctx)

    outside = _adapter("conv")._build_options(resume=None)
    assert outside.can_use_tool is None
