"""The scheduled tasks `/status` lists, and the button that cancels one (spec
channels "List and cancel a chat's scheduled tasks from /status").

`/status` shows what waits in the conversation it is about: each task's next
time and name, soonest first, with a Cancel button per task where the
transport has buttons. The tap is owner-gated like every card tap and removes
the task.

The tasks themselves belong to the scheduled-task core, which is wired after
the commands exist; the composition root hands its reader in as
:attr:`ChannelCommands.scheduled` (``None`` lists nothing).

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from coffer.domain.channel.envelopes import ChoiceButton

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["TASK_CANCEL_KIND", "ChatTasksPort", "WaitingTaskLine", "cancel_tapped", "task_lines"]

#: The callback namespace of a task's Cancel button: ``taskx:<task uid>``.
TASK_CANCEL_KIND = "taskx"

#: The most tasks `/status` lists by name.
_SHOWN = 5


@dataclass(frozen=True)
class WaitingTaskLine:
    uid: str
    name: str
    next_run: datetime | None


class ChatTasksPort(Protocol):
    async def waiting(
        self, channel_uid: str, chat_id: str, conversation_thread_id: str
    ) -> list[WaitingTaskLine]: ...

    async def cancel(self, uid: str, *, actor: str) -> str | None:
        """Remove the task; its name, or ``None`` when there was none."""
        ...


def _when(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    local = moment.astimezone()
    today = datetime.now().astimezone().date()
    return f"{local:%H:%M}" if local.date() == today else f"{local:%m-%d %H:%M}"


async def task_lines(ctx: CommandContext) -> tuple[list[str], list[ChoiceButton]]:
    """The `/status` lines for this conversation's waiting tasks, and their
    Cancel buttons."""
    port = ctx.commands.scheduled
    if port is None:
        return [], []
    waiting = await port.waiting(ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id)
    if not waiting:
        return [], []
    lines = ["Scheduled:"]
    buttons = []
    for n, task in enumerate(waiting[:_SHOWN], 1):
        lines.append(f"⏰ {n}. {_when(task.next_run)} {task.name}")
        buttons.append(ChoiceButton(label=f"Cancel ⏰{n}", value=f"{TASK_CANCEL_KIND}:{task.uid}"))
    if len(waiting) > _SHOWN:
        lines.append(f"… and {len(waiting) - _SHOWN} more on the Scheduled tasks page")
    return lines, buttons


async def cancel_tapped(ctx: CommandContext, uid: str) -> None:
    port = ctx.commands.scheduled
    if port is None:
        return
    name = await port.cancel(uid, actor=f"channel:{ctx.binding.resource.name}")
    await ctx.say(f"🗑 Cancelled “{name}”." if name else "That task is already gone.")
