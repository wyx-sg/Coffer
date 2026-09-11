"""The channel command roster — one source for the help text, the dispatch
switch, and the platform's own command menu.

FR-065: a command the help text offers but the registered menu omits is a
drift bug, not a design choice. Both are derived from :data:`COMMAND_ROSTER`
here, so they cannot disagree; a new command is one tuple entry plus its
handler branch.

Pure domain data — no I/O, no platform vocabulary. A transport translates
these into whatever shape its own menu API wants.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["COMMAND_ROSTER", "ChannelCommand", "help_text", "is_group_private", "names"]


@dataclass(frozen=True)
class ChannelCommand:
    """One slash command the channel handles."""

    #: Without the leading slash. Telegram's menu accepts lowercase letters,
    #: digits and underscores only, which every entry here satisfies.
    name: str
    #: A short argument hint for the help text (``"[key]"``), or "" when the
    #: command takes none. Never part of the registered menu entry.
    args: str
    #: One line, ≤ 256 characters — used verbatim both in the help text and as
    #: the platform menu's description.
    description: str
    #: FR-064: the answer is for the asker alone, so in a group it is delivered
    #: privately where the transport can (Telegram ephemeral messages) rather
    #: than announced to the room. ``/new`` and ``/stop`` change shared state
    #: and stay visible; the rest are the asker's own business.
    group_private: bool = False


COMMAND_ROSTER: tuple[ChannelCommand, ...] = (
    ChannelCommand("new", "", "Start a fresh conversation"),
    ChannelCommand("agent", "[key]", "Show or switch the agent (opens a fresh conversation)", True),
    ChannelCommand("model", "[name]", "Show or switch the model (next turn)", True),
    ChannelCommand("stop", "", "Interrupt the running turn"),
    ChannelCommand("status", "", "Conversation, agent, and turn state", True),
    ChannelCommand("help", "", "List the commands", True),
)


def names() -> frozenset[str]:
    """Every handled command as its typed form (``"/help"``)."""
    return frozenset(f"/{command.name}" for command in COMMAND_ROSTER)


def is_group_private(command: str) -> bool:
    """Whether ``command`` (typed form, e.g. ``"/status"``) answers the asker
    alone rather than the room (FR-064). An unknown command is private: an
    "unknown command" scolding is the least useful thing to broadcast."""
    wanted = command.lstrip("/").lower()
    for entry in COMMAND_ROSTER:
        if entry.name == wanted:
            return entry.group_private
    return True


def help_text() -> str:
    """The ``/help`` body, rendered from the roster."""
    lines = ["Coffer channel commands:"]
    for command in COMMAND_ROSTER:
        head = f"/{command.name} {command.args}".rstrip()
        lines.append(f"{head} — {command.description}")
    return "\n".join(lines)
