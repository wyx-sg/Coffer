"""Claude Code's ``AskUserQuestion`` as a Coffer question (spec chat "Pause a turn
on a question for the owner").

Under ``bypassPermissions`` the CLI still asks for permission to a tool that
requires user interaction, before the bypass applies, so the adapter's
``can_use_tool`` callback is consulted for ``AskUserQuestion`` (verified against
the bundled CLI; the change's design §3).
"""

from __future__ import annotations

import warnings
from typing import Any

from claude_agent_sdk import (
    CanUseToolShadowedWarning,
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
)

from coffer.application.chat.question_agents import AskOwner
from coffer.domain.chat.question import QuestionBlock

# The SDK warns that ``can_use_tool`` is shadowed under ``bypassPermissions``. It is
# not for the one tool this callback serves.
warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning)

#: The tool Claude Code uses to put a multiple-choice dialog in front of the user.
ASK_USER_QUESTION = "AskUserQuestion"


def question_answers(block: QuestionBlock) -> dict[str, str]:
    """``AskUserQuestion``'s ``answers`` field: the question text -> the answer
    (several chosen labels joined with ", ")."""
    return {q.question: a.display() for q, a in zip(block.questions, block.answers, strict=False)}


async def permission_for(
    ask_owner: AskOwner | None, tool_name: str, tool_input: dict[str, Any]
) -> PermissionResult:
    """Turn ``AskUserQuestion`` into a Coffer question and hand the answers back
    as the tool's own ``answers``; every other tool is allowed as it would be under
    ``bypassPermissions`` (the CLI does not consult the callback for them)."""
    if tool_name != ASK_USER_QUESTION or ask_owner is None:
        return PermissionResultAllow()
    try:
        outcome = await ask_owner(tool_input)
    except ValueError as exc:
        return PermissionResultDeny(message=f"Could not ask the owner: {exc}")
    if not outcome.answered:
        return PermissionResultDeny(message=outcome.message or "The owner did not answer.")
    return PermissionResultAllow(
        updated_input={**tool_input, "answers": question_answers(outcome.block)}
    )
