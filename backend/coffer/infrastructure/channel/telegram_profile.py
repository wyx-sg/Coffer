"""What the bot says about itself, and what the platform says about the bot.

Two halves of the same start-up conversation with Telegram:

* :func:`probe_identity` reads ``getMe`` for the fields that change what the
  transport may do — the bot's own id/username (@mention matching) and whether
  privacy mode leaves it able to read group messages (FR-059/FR-060).
* :func:`register_profile` pushes Coffer's command roster into the platform's
  command menu and fills an empty profile so a first-time user does not open a
  blank chat (FR-065).

A helper module beside ``telegram.py`` so that file stays inside the size cap.
Every call here is best-effort: a bot that cannot describe itself still works.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from coffer.domain.channel.commands import COMMAND_ROSTER

__all__ = ["BotIdentity", "menu_commands", "probe_identity", "register_profile"]

_logger = logging.getLogger(__name__)

Call = Callable[..., Awaitable[Any]]

#: Telegram caps these; both are truncated rather than rejected outright so a
#: future edit to the copy cannot start failing start-up.
_DESCRIPTION_LIMIT = 512
_SHORT_DESCRIPTION_LIMIT = 120

_DESCRIPTION = (
    "Coffer bridges this chat to the AI coding agents on your own machine. "
    "Pair once, then talk normally — send text, photos, or files and the "
    "agent answers here. /agent switches which agent replies, /model switches "
    "its model, and each group topic keeps its own conversation."
)
_SHORT_DESCRIPTION = "Talk to the AI coding agents on your own machine."


@dataclass(frozen=True)
class BotIdentity:
    """What ``getMe`` told us. Every field degrades to a safe default when the
    call failed, so a transport that could not introspect itself still runs —
    it just cannot match @mentions or diagnose privacy mode."""

    bot_id: int | None = None
    username: str | None = None
    #: ``True`` when privacy mode is DISABLED, i.e. the bot receives ordinary
    #: group messages. ``None`` when unknown (``getMe`` failed, or an older Bot
    #: API server omitted the field) — an unknown state is never reported as a
    #: problem, only a known-restrictive one is (FR-060).
    reads_all_group_messages: bool | None = None


async def probe_identity(call: Call) -> BotIdentity:
    """Read ``getMe``; never raise. FR-059: what the platform says about itself
    is probed at start-up, not assumed."""
    try:
        me = await call("getMe")
    except Exception:
        _logger.warning("telegram.getme.failed", exc_info=True)
        return BotIdentity()
    if not isinstance(me, dict):
        return BotIdentity()
    raw_id = me.get("id")
    raw_privacy = me.get("can_read_all_group_messages")
    return BotIdentity(
        bot_id=int(raw_id) if isinstance(raw_id, int) else None,
        username=str(me["username"]) if me.get("username") else None,
        reads_all_group_messages=raw_privacy if isinstance(raw_privacy, bool) else None,
    )


def menu_commands() -> list[dict[str, Any]]:
    """The command roster in Telegram's ``BotCommand`` shape (FR-065).

    Every handled command is listed — the menu is generated from the same
    roster the help text is, so the two cannot drift apart.

    An asker-only command is registered as ephemeral (FR-064): typing it in a
    group does not put it in front of everyone, and it hands the bot the handle
    it needs to answer that member privately without being an administrator.
    """
    return [
        {
            "command": entry.name,
            "description": entry.description,
            "is_ephemeral": entry.group_private,
        }
        for entry in COMMAND_ROSTER
    ]


async def register_profile(call: Call) -> None:
    """Register the command menu and fill an empty profile (FR-065).

    The command menu is Coffer's functional contract and is always written.
    The prose profile is only *filled in*, never overwritten: the name and any
    description the owner set in BotFather are their branding decision, so a
    bot that already describes itself is left exactly as it is.
    """
    await _try(call, "setMyCommands", commands=menu_commands())
    # A menu button showing the command list is strictly better than the
    # default blank one, and carries no copy of its own to overwrite.
    await _try(call, "setChatMenuButton", menu_button={"type": "commands"})
    await _fill_if_empty(
        call,
        "getMyDescription",
        "setMyDescription",
        "description",
        _DESCRIPTION,
        _DESCRIPTION_LIMIT,
    )
    await _fill_if_empty(
        call,
        "getMyShortDescription",
        "setMyShortDescription",
        "short_description",
        _SHORT_DESCRIPTION,
        _SHORT_DESCRIPTION_LIMIT,
    )


async def _fill_if_empty(
    call: Call, getter: str, setter: str, field: str, value: str, limit: int
) -> None:
    """Write ``value`` only when the platform reports the field as empty."""
    try:
        current = await call(getter)
    except Exception:
        return  # cannot tell whether it is set — leave the owner's bot alone
    if not isinstance(current, dict) or str(current.get(field) or "").strip():
        return
    await _try(call, setter, **{field: value[:limit]})


async def _try(call: Call, method: str, **params: Any) -> None:
    """One best-effort start-up call: a bot that cannot describe itself still
    serves turns, so a failure is logged and swallowed."""
    try:
        await call(method, **params)
    except Exception:
        _logger.warning("telegram.profile.failed", extra={"method": method}, exc_info=True)
