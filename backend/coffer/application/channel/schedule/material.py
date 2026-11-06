"""What the daily report is written from: the day's channel conversations
(spec channels "Write the daily report from the day's channel conversations").

Coffer keeps an index of each conversation and nothing that was said, so the
material is assembled at the moment the report runs: the index says which
conversations were active today, where they live and which agent session holds
them; the agent's own record of that session gives the last thing asked and the
first line of the last answer (ADR
scheduled-tasks-are-turns-coffer-starts-in-a-chat, "What the report reads").
To that the scheduled runs of the day are added — what ran, what was skipped
and why — and the tasks still waiting.

Everything read from a session is untrusted text and is neutralised before it
joins the turn.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from coffer.application.channel.schedule.message import local_time
from coffer.application.channel.schedule.ports import SessionTail, SessionTailPort
from coffer.application.channel.store_ports import ChannelThreadConversationRepoPort
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.turn_markers import USER, USER_END, neutralise

__all__ = ["DayConversation", "WaitingTask", "channel_day", "human_words"]

#: The most conversations one report reads; a busier day lists the rest by count.
MAX_CONVERSATIONS = 40
#: How much of what was asked, and of the answer's first line, a report gets.
_ASKED_CHARS = 300
_ANSWER_CHARS = 200

_USER_BLOCK = re.compile(
    r"^\[" + re.escape(USER) + r"[^\]]*\]\n(.*?)\n\[" + re.escape(USER_END) + r"\]",
    re.MULTILINE | re.DOTALL,
)

#: One page of channel conversations, newest activity first, and the cursor on.
PageConversations = Callable[[str | None], Awaitable[tuple[Sequence[Any], str | None]]]


@dataclass(frozen=True)
class DayConversation:
    channel: str
    chat_kind: str
    in_thread: bool
    title: str
    updated_at: datetime
    tail: SessionTail


@dataclass(frozen=True)
class WaitingTask:
    name: str
    next_run: datetime
    where: str


def human_words(text: str) -> str:
    """The person's own words out of a channel turn's text: the user-message
    blocks, without the origin and thread blocks around them. Text that has no
    such block (a terminal session) is returned whole."""
    found = _USER_BLOCK.findall(text)
    return "\n".join(part.strip() for part in found) if found else text.strip()


def _clip(text: str, limit: int) -> str:
    one = " ".join(text.split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


async def day_conversations(
    *,
    since: datetime,
    page: PageConversations,
    threads: ChannelThreadConversationRepoPort,
    tails: SessionTailPort | None,
    channel_names: Mapping[str, str],
    exclude: set[str],
) -> tuple[list[DayConversation], int]:
    """Channel conversations active since ``since`` (newest first, at most
    :data:`MAX_CONVERSATIONS` read) and how many there were in all."""
    found: list[Any] = []
    cursor: str | None = None
    while True:
        items, cursor = await page(cursor)
        fresh = [c for c in items if c.updated_at >= since and c.id not in exclude]
        found.extend(fresh)
        if cursor is None or not items or items[-1].updated_at < since:
            break
    located = await threads.locate_many([c.id for c in found[:MAX_CONVERSATIONS]])
    out: list[DayConversation] = []
    for conv in found[:MAX_CONVERSATIONS]:
        loc = located.get(conv.id)
        session_id = conv.agent_config.session_id
        tail = SessionTail(asked="", answered="")
        if tails is not None and session_id:
            try:
                tail = await tails.tail(conv.agent_key, session_id, conv.agent_config.cwd)
            except Exception:
                tail = SessionTail(asked="", answered="")
        out.append(
            DayConversation(
                channel=channel_names.get(conv.channel_uid or "", conv.channel_uid or ""),
                chat_kind=(loc[0].chat_kind if loc else "") or "direct",
                in_thread=bool(loc and loc[0].thread_id),
                title=conv.title,
                updated_at=conv.updated_at,
                tail=tail,
            )
        )
    return out, len(found)


def _run_line(run: ScheduledRun) -> str:
    what: str = run.outcome
    if run.reason:
        what += f": {run.reason}"
    return f"- {local_time(run.due_at)} {neutralise(run.task_name)} — {what}"


def channel_day(
    *,
    since: datetime,
    conversations: Sequence[DayConversation],
    total: int,
    runs: Sequence[ScheduledRun],
    waiting: Sequence[WaitingTask],
) -> str:
    """The material as text. ``""`` when there were no conversations at all —
    the daily report then does not run (spec channels "Skip the daily report on
    a day with no conversations")."""
    if not conversations:
        return ""
    lines = [f"Channel conversations since {local_time(since)}: {total}"]
    for n, conv in enumerate(conversations, 1):
        where = f"{conv.channel} · {conv.chat_kind}" + (" · thread" if conv.in_thread else "")
        lines.append(
            f"{n}. [{where}] {neutralise(_clip(conv.title, 80))} · last active "
            f"{local_time(conv.updated_at)}"
        )
        asked = _clip(human_words(conv.tail.asked), _ASKED_CHARS)
        if asked:
            lines.append(f"   last asked: {neutralise(asked)}")
        answer = _clip(_first_line(conv.tail.answered), _ANSWER_CHARS)
        if answer:
            lines.append(f"   answer began: {neutralise(answer)}")
    if total > len(conversations):
        lines.append(f"… and {total - len(conversations)} more not read here.")
    if runs:
        lines.append("")
        lines.append("Scheduled runs today:")
        lines.extend(_run_line(r) for r in runs)
    if waiting:
        lines.append("")
        lines.append("Scheduled tasks still waiting:")
        lines.extend(
            f"- {local_time(w.next_run)} {neutralise(w.name)} ({w.where})" for w in waiting
        )
    return "\n".join(lines)
