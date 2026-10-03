"""`/dir [path|name]` — the working directory, from the channel's allow-list
only (spec channels "Choose the working directory from chat").

A phone must not be able to point an agent at any directory on the machine,
so `/dir` reaches exactly the directories the owner listed for the channel
(``ChannelBinding.directories``): an entry itself, a directory under one, or
the basename of exactly one. It must exist. Because an agent session is tied
to its directory, a switch records the sticky directory and opens a fresh
conversation there — the previous one stays one `/resume` away. `/dir default`
clears it; bare `/dir` shows what is in effect and the allow-list as a card.

In a SeaTalk group's main chat only the group's default is written (spec
channels "Set a group's defaults from its main chat").

Application layer only: plain ``os.path`` reads, no infrastructure import.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from coffer.application.channel.command_text import GROUP_DEFAULT_SUFFIX, default_cwd
from coffer.application.channel.new_conversation import open_fresh
from coffer.application.channel.selection_cards import SelectionCard, dir_card, path_label

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["NO_DIRECTORIES", "apply_dir", "cmd_dir", "current_dir_card", "resolve_dir"]

#: What `/dir` says for a channel whose allow-list is empty: `/dir` is off.
NO_DIRECTORIES = (
    "/dir is off for this bot — no directories are allowed for it. In Coffer, open "
    "Channels, the bot, Settings, and add them under Working directories; or run "
    "`coffer channel edit <name> --dir PATH`."
)


def _real(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def _base(path: str) -> str:
    return os.path.basename(os.path.normpath(path))


def resolve_dir(directories: tuple[str, ...], typed: str) -> tuple[str | None, str]:
    """``(path, "")`` for the directory ``typed`` names within ``directories``,
    or ``(None, refusal)``."""
    allowed = ", ".join(directories)
    expanded = os.path.expanduser(typed)
    if os.path.isabs(expanded):
        wanted = _real(expanded)
        path = next((d for d in directories if _real(d) == wanted), None)
        if path is None and any(
            wanted.startswith(_real(d).rstrip(os.sep) + os.sep) for d in directories
        ):
            path = os.path.normpath(expanded)
    else:
        named = [d for d in directories if _base(d) == typed.rstrip("/")]
        if len(named) > 1:
            return (
                None,
                f"'{typed}' names more than one allowed directory — send the full path: {allowed}",
            )
        path = named[0] if named else None
    if path is None:
        return None, f"🚫 '{typed}' is not an allowed directory. Allowed: {allowed}"
    if not os.path.isdir(path):
        return None, f"⚠️ {path} is not an existing directory."
    return path, ""


async def cmd_dir(ctx: CommandContext, text: str) -> None:
    directories = ctx.binding.directories
    typed = " ".join(text.split()[1:])
    if not typed:
        await _show(ctx)
        return
    if typed.lower() == "default":
        await apply_dir(ctx, None)
        return
    if not directories:
        await ctx.say(NO_DIRECTORIES)
        return
    path, refusal = resolve_dir(directories, typed)
    if path is None:
        await ctx.say(refusal)
        return
    await apply_dir(ctx, path)


async def apply_dir(ctx: CommandContext, path: str | None) -> None:
    """Stick ``path`` (``None`` = the channel's default) on the thread and open
    a fresh conversation there. Shared by the typed form and a card tap."""
    await ctx.commands._threads.set_preferences(
        ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id, cwd=path
    )
    shown = path_label(path or default_cwd(ctx.binding))
    if ctx.group_main:
        await ctx.say(f"📁 Directory set to {shown}{GROUP_DEFAULT_SUFFIX}.")
        return
    if await open_fresh(ctx):
        await ctx.say(f"📁 Now in {shown} — started a fresh conversation.")


async def current_dir_card(ctx: CommandContext, *, page: int | None = None) -> SelectionCard:
    settings = await ctx.settings()
    return dir_card(
        current=settings.cwd,
        directories=ctx.binding.directories,
        default=default_cwd(ctx.binding),
        page=page,
    )


async def _show(ctx: CommandContext) -> None:
    settings = await ctx.settings()
    directories = ctx.binding.directories
    if directories and not ctx.group_main and await ctx.show(await current_dir_card(ctx)):
        return
    lines = [f"📁 Working directory: {path_label(settings.cwd)}"]
    if directories:
        lines.append("Allowed:")
        lines += [f"{n}. {path_label(path)}" for n, path in enumerate(directories, start=1)]
        lines.append("Send /dir <path|name> or /dir default.")
    else:
        lines.append(NO_DIRECTORIES)
    await ctx.say("\n".join(lines))
