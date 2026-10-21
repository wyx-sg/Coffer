"""The channel command roster — one source for the help text, the dispatch
switch, the typo guard and the platform's own command menus.

A command the help text offers but the registered menu omits is a drift bug,
not a design choice (spec channels "Register the bot's command menu and
profile from one roster"). Everything is derived from :data:`COMMAND_ROSTER`
here, so nothing can disagree; a new command is one entry plus its handler.

Ten words are reserved and nothing else (spec channels "Pass unreserved slash
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
        "Start a fresh conversation, optionally on another agent",
        "开始新对话，可指定换一个智能体",  # noqa: RUF001
    ),
    ChannelCommand("stop", "", "Stop what\u2019s running", "停止正在运行的任务"),
    ChannelCommand(
        "status",
        "",
        "What\u2019s running, and the agent, model and directory in use",
        "正在运行什么，以及当前的智能体、模型和目录",  # noqa: RUF001
        dm_only=True,
    ),
    ChannelCommand(
        "model",
        "[name]",
        "Switch the model",
        "切换模型",
        dm_only=True,
    ),
    ChannelCommand(
        "dir",
        "[path|name]",
        "Switch the working directory",
        "切换工作目录",
        dm_only=True,
    ),
    ChannelCommand(
        "resume",
        "[n]",
        "Go back to an earlier conversation",
        "回到之前的对话",
        dm_only=True,
    ),
    ChannelCommand(
        "thread",
        "[title]",
        "Open a parallel conversation beside this chat",
        "在旁边开一个并行对话",
        dm_only=True,
    ),
    ChannelCommand(
        "close",
        "",
        "Close this parallel thread",
        "关闭这个并行对话",
        dm_only=True,
    ),
    ChannelCommand(
        "del",
        "",
        "Withdraw my latest reply (reply to one of mine to pick it)",
        "撤回我最近的一条回复（引用某条回复可指定撤回它）",  # noqa: RUF001
        group_private=True,
    ),
    ChannelCommand("help", "", "This list of commands", "命令列表", group_private=True),
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
    """The ``/help`` body, rendered from the roster: a heading, then one line per
    command — its typed form with arguments and what it does — then what anything
    else is (spec channels "List the commands with /help"). A group's help lists
    only the group commands and says where the others work."""
    lines = ["**Commands**"]
    lines += [
        f"/{c.name} {c.args}".rstrip() + f" \u2014 {c.description}"
        for c in menu_entries(group=group)
    ]
    lines.append("")
    if group:
        lines.append("The other commands work in a private chat with me.")
    lines.append("Anything else goes to the agent as a message.")
    return "\n".join(lines)
