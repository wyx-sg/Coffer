"""The channel command roster — one source for the help text, the dispatch
switch, the typo guard and the platform's own command menus.

A command the help text offers but the registered menu omits is a drift bug,
not a design choice (spec channels "Register the bot's command menu and
profile from one roster"). Everything is derived from :data:`COMMAND_ROSTER`
here, so nothing can disagree; a new command is one entry plus its handler.

Nine words are reserved and nothing else (spec channels "Pass unreserved slash
text to the agent"): a text is a command only when its first word names an
entry here, a near-miss of one answers "Did you mean", and anything else that
starts with ``/`` — a path, an agent's own ``/compact`` — is a message for the
agent.

Pure domain data — no I/O, no platform vocabulary. A transport translates
these into whatever shape its own menu API wants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "COMMAND_ROSTER",
    "DM_ONLY_NOTICE",
    "HIDDEN_ALIASES",
    "ChannelCommand",
    "command_name",
    "help_text",
    "is_dm_only",
    "is_group_private",
    "menu_entries",
    "names",
    "near_miss",
]


@dataclass(frozen=True)
class ChannelCommand:
    """One slash command the channel handles."""

    #: Without the leading slash. Telegram's menu accepts lowercase letters,
    #: digits and underscores only, which every entry here satisfies.
    name: str
    #: A short argument hint for the help text (``"[agent]"``), or "".
    args: str
    #: One line, ≤ 256 characters — the help text and the English menu entry.
    description: str
    #: The same line in Chinese, for a menu registered with ``language_code=zh``.
    description_zh: str
    #: "Keep non-answer chatter private in a group": the answer is for the
    #: asker alone, so in a group it is delivered privately where the transport
    #: can. ``/new`` and ``/stop`` stay visible. A ``dm_only`` command's notice
    #: in a group is always private (see :func:`is_group_private`).
    group_private: bool = False
    #: The command works only in a direct chat (spec channels "Answer the
    #: conversation commands from any paired chat"): in a group it is answered
    #: with :data:`DM_ONLY_NOTICE` and does nothing, and a group's menu and help
    #: leave it out (spec channels/telegram "Register command menus per chat
    #: scope and language").
    dm_only: bool = False


COMMAND_ROSTER: tuple[ChannelCommand, ...] = (
    ChannelCommand(
        "new",
        "[agent]",
        "Start a fresh conversation [agent]",
        "开始新对话 [agent]",
    ),
    ChannelCommand("stop", "", "Stop what\u2019s running", "停止正在运行的任务"),
    ChannelCommand(
        "model",
        "[name]",
        "Pick a model",
        "选择模型",
        dm_only=True,
    ),
    ChannelCommand(
        "dir",
        "[path|name]",
        "Pick the working directory",
        "选择工作目录",
        dm_only=True,
    ),
    ChannelCommand(
        "status",
        "",
        "What is running, threads",
        "正在运行的内容与线程",
        dm_only=True,
    ),
    ChannelCommand(
        "resume",
        "[n]",
        "Go back to a conversation",
        "回到某个历史对话",
        dm_only=True,
    ),
    ChannelCommand(
        "thread",
        "[title]",
        "Open a parallel thread",
        "开启并行线程",
        dm_only=True,
    ),
    ChannelCommand(
        "del",
        "",
        "Withdraw a reply",
        "撤回一条回复",
        group_private=True,
    ),
    ChannelCommand("help", "", "Commands", "命令列表", group_private=True),
)

#: The one line a group gets when it sends a direct-chat-only command, in English
#: and Chinese (spec channels "Answer the conversation commands from any paired
#: chat"). Delivered privately to the sender; the command itself does nothing.
DM_ONLY_NOTICE = "This command works in a private chat with me. / 此命令请在与我的私聊中使用。"

#: Typed forms that run a roster command but are never listed: ``/start`` is
#: what Telegram's start button and pairing link send.
HIDDEN_ALIASES: dict[str, str] = {"start": "help"}

_HEAD = re.compile(r"^/([A-Za-z0-9_]+)$")


def names() -> frozenset[str]:
    """Every handled command as its typed form (``"/help"``)."""
    return frozenset(f"/{c.name}" for c in COMMAND_ROSTER)


def command_name(text: str) -> str | None:
    """The roster name ``text`` invokes (``"/Model opus"`` → ``"model"``), or
    ``None`` when its first word is not a reserved command.

    Hidden aliases resolve to what they stand for (``/start`` → ``help``).
    """
    words = text.split()
    if not words:
        return None
    match = _HEAD.match(words[0])
    if match is None:
        return None
    head = match.group(1).lower()
    head = HIDDEN_ALIASES.get(head, head)
    return head if any(c.name == head for c in COMMAND_ROSTER) else None


def _distance(a: str, b: str) -> int:
    """Edit distance counting a swap of two neighbours as one edit (``/stpo`` is
    one slip from ``/stop``); the words compared here are a few letters long."""
    rows = [list(range(len(b) + 1))] + [[i] + [0] * len(b) for i in range(1, len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[len(a)][len(b)]


def near_miss(text: str) -> str | None:
    """The command ``text`` most likely meant (``"/stpo"`` → ``"stop"``), or
    ``None`` when it is not close to any — then it is a message for the agent.

    Only a single slash-word can be a typo: ``/Users/me/app`` (a path) and
    ``/review`` (an agent's own command, far from every reserved word) pass
    through. The tolerance is one edit for names of four letters or fewer and
    two for longer ones, so ``/stat`` finds ``/status`` and ``/new`` never
    swallows ``/now``-style words that are further away.
    """
    words = text.split()
    if not words:
        return None
    match = _HEAD.match(words[0])
    if match is None:
        return None
    head = match.group(1).lower()
    if command_name(words[0]) is not None:
        return None
    best: tuple[int, str] | None = None
    for entry in COMMAND_ROSTER:
        limit = 1 if len(entry.name) <= 4 else 2
        distance = _distance(head, entry.name)
        if distance <= limit and (best is None or distance < best[0]):
            best = (distance, entry.name)
    return best[1] if best is not None else None


def is_group_private(command: str) -> bool:
    """Whether ``command`` (typed form, e.g. ``"/status"``) answers the asker
    alone rather than the room ("Keep non-answer chatter private in a group").
    Anything not on the roster — a "Did you mean" line — is private: a
    correction is the least useful thing to broadcast."""
    name = command_name(command)
    for entry in COMMAND_ROSTER:
        if entry.name == name:
            return entry.group_private or entry.dm_only
    return True


def is_dm_only(command: str) -> bool:
    """Whether ``command`` (typed form) works only in a direct chat."""
    name = command_name(command)
    return any(entry.name == name and entry.dm_only for entry in COMMAND_ROSTER)


def menu_entries(*, group: bool) -> tuple[ChannelCommand, ...]:
    """The commands a menu offers: every one in a private chat, only the group
    commands (``/new``, ``/stop``, ``/help``) in a group."""
    return tuple(c for c in COMMAND_ROSTER if not c.dm_only) if group else COMMAND_ROSTER


def help_text(*, group: bool = False) -> str:
    """The ``/help`` body, rendered from the roster: every command with its
    arguments on one line (a group's help lists only the group commands), then
    what anything else is. The one-line descriptions live in the platform's own
    command menu (Telegram)."""
    heads = [f"/{c.name} {c.args}".rstrip() for c in menu_entries(group=group)]
    return " · ".join(heads) + "\nAnything else is a message to the agent."
