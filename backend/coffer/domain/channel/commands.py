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
    "EFFORT_LEVELS",
    "HIDDEN_ALIASES",
    "ChannelCommand",
    "command_name",
    "help_text",
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
    #: can. ``/new``, ``/stop``, ``/thread`` and ``/kb`` stay visible.
    group_private: bool = False
    #: Whether the command is offered in a group's menu (spec channels/telegram
    #: "Register command menus per chat scope and language").
    in_group_menu: bool = False
    #: Offered only while the ``knowledge`` feature is on.
    needs_knowledge: bool = False


COMMAND_ROSTER: tuple[ChannelCommand, ...] = (
    ChannelCommand(
        "new",
        "[agent]",
        "Start a fresh conversation (keeps model, effort and directory)",
        "开始新对话并保留模型、推理强度和目录",
        in_group_menu=True,
    ),
    ChannelCommand(
        "stop", "", "Interrupt the running turn", "中断正在运行的回合", in_group_menu=True
    ),
    ChannelCommand(
        "model",
        "[name] [level]",
        "Show or set the model and reasoning effort",
        "查看或设置模型与推理强度",
        group_private=True,
        in_group_menu=True,
    ),
    ChannelCommand(
        "dir",
        "[path|name]",
        "Show or switch the working directory (starts a fresh conversation)",
        "查看或切换工作目录并开始新对话",
        group_private=True,
    ),
    ChannelCommand(
        "status",
        "",
        "What this chat is running, with quick actions",
        "当前对话状态与快捷操作",
        group_private=True,
        in_group_menu=True,
    ),
    ChannelCommand(
        "resume",
        "[n]",
        "Reopen an earlier conversation from this chat",
        "回到本聊天中的某个历史对话",
        group_private=True,
        in_group_menu=True,
    ),
    ChannelCommand(
        "thread",
        "[title]",
        "Open a parallel conversation in its own thread",
        "在新线程中开启并行对话",
    ),
    ChannelCommand(
        "kb",
        "[collection]",
        "Save the document you just sent into a knowledge collection",
        "把刚发送的文档存入知识库集合",
        needs_knowledge=True,
    ),
    ChannelCommand(
        "help", "", "List the commands", "列出所有命令", group_private=True, in_group_menu=True
    ),
)

#: Typed forms that run a roster command but are never listed: ``/start`` is
#: what Telegram's start button and pairing link send.
HIDDEN_ALIASES: dict[str, str] = {"start": "help"}

#: The closed vocabulary ``/model <level>`` recognises as an effort level rather
#: than a model name — no model id either agent ships is one of these words.
EFFORT_LEVELS: frozenset[str] = frozenset({"minimal", "low", "medium", "high", "xhigh", "max"})

_HEAD = re.compile(r"^/([A-Za-z0-9_]+)$")


def _entries(*, knowledge: bool) -> tuple[ChannelCommand, ...]:
    return tuple(c for c in COMMAND_ROSTER if knowledge or not c.needs_knowledge)


def names(*, knowledge: bool = True) -> frozenset[str]:
    """Every handled command as its typed form (``"/help"``)."""
    return frozenset(f"/{c.name}" for c in _entries(knowledge=knowledge))


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
            return entry.group_private
    return True


def menu_entries(*, group: bool, knowledge: bool) -> tuple[ChannelCommand, ...]:
    """The commands a menu offers: every one in a private chat, the group subset
    in a group; ``/kb`` only while knowledge is on."""
    entries = _entries(knowledge=knowledge)
    return tuple(c for c in entries if c.in_group_menu) if group else entries


def help_text(*, knowledge: bool = True) -> str:
    """The ``/help`` body, rendered from the roster: every command with its
    arguments on one line, then what anything else is. The one-line
    descriptions live in the platform's own command menu (Telegram)."""
    heads = [f"/{c.name} {c.args}".rstrip() for c in _entries(knowledge=knowledge)]
    return " · ".join(heads) + "\nAnything else is a message to the agent."
