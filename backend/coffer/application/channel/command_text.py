"""The words a command answer is written in — names a person reads, never keys.

Every answer a channel command gives names an agent, a model or a directory,
and each has two spellings: the one Coffer stores (``claude_code``,
``claude-opus-4-8``, ``/Users/me/src/app``) and the one a person recognises
(``Claude Code``, ``Opus 4.8``, ``app``). This module is the one place the
second is derived from the first, so a `/status` line, a `/new` confirmation
and an "Unknown agent" refusal can never disagree about what a thing is called
(spec channels "Switch the agent with /new": keys never appear in an answer).

It also holds the settings a thread is on right now — its own sticky choice,
else (in a group thread) the group's, else the channel's defaults — because
that is what those answers describe.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from coffer.application.channel.agent_routing import effective_agent, routable_choices
from coffer.application.channel.conversation_ops import inherited_setting
from coffer.application.channel.selection_cards import path_label
from coffer.domain.chat.errors import ConversationNotFound

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands
    from coffer.application.channel.ports import AgentCatalogPort, ChannelBinding
    from coffer.application.channel.store_ports import ChannelPeer

__all__ = [
    "GROUP_DEFAULT_SUFFIX",
    "NO_AGENT_IN_SCOPE",
    "Settings",
    "age",
    "agent_display",
    "default_cwd",
    "default_model_text",
    "dir_display",
    "model_display",
    "resolve_agent",
    "settings_in_effect",
    "settings_line",
    "typable_name",
    "unknown_agent",
]

#: What a setting sent in a SeaTalk group's main chat ends with (spec channels
#: "Set a group's defaults from its main chat").
GROUP_DEFAULT_SUFFIX = " — default for new threads in this group"

#: What `/new <agent>` says when the channel's scope leaves it no agent to
#: offer: every agent its scope names is one this machine has not added. It
#: must still name the cause rather than answering with an empty list.
NO_AGENT_IN_SCOPE = (
    "None of the agents this bot may use is set up on this machine. "
    "Change its reach in Coffer to use it."
)


def typable_name(key: str) -> str:
    """The resource-style name an agent is typed as (``claude_code`` → ``claude-code``)."""
    return key.replace("_", "-")


def agent_display(agents: AgentCatalogPort, key: str) -> str:
    """The agent's display name, or its typable name when the registry has none."""
    return dict(agents.agent_choices()).get(key) or typable_name(key)


def _fold(name: str) -> str:
    """``Claude Code``, ``claude-code`` and ``claude_code`` all fold to one form."""
    return "".join("_" if c in "-_ " else c for c in name.strip().lower())


def resolve_agent(binding: ChannelBinding, agents: AgentCatalogPort, typed: str) -> str | None:
    """The key of the routable agent ``typed`` names — its display name or its
    resource-style name, case-insensitive, ``-``/``_``/space alike — or ``None``.

    Only agents this channel may drive are candidates (ADR
    per-agent-resource-scope), so a name outside the scope is simply unknown."""
    wanted = _fold(typed)
    for key, display in routable_choices(binding, agents):
        if wanted in (_fold(key), _fold(display)):
            return key
    return None


def unknown_agent(binding: ChannelBinding, agents: AgentCatalogPort, typed: str) -> str:
    """The refusal for a name no routable agent answers to, listing the ones
    that do by the names a person types them as."""
    choices = routable_choices(binding, agents)
    if not choices:
        return NO_AGENT_IN_SCOPE
    listing = ", ".join(f"{display} ({typable_name(key)})" for key, display in choices)
    return f"Unknown agent '{typed}'. Available: {listing}"


def dir_display(path: str | None) -> str:
    """A directory as a person reads it (``~/src/app``), or ``Default directory``."""
    return path_label(path)


def age(when: datetime, *, now: datetime | None = None) -> str:
    """How long ago ``when`` was: ``just now``, ``5m ago``, ``2h ago``,
    ``yesterday``, ``3d ago``."""
    moment = when if when.tzinfo is not None else when.replace(tzinfo=UTC)
    seconds = max(0.0, ((now or datetime.now(tz=UTC)) - moment).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    days = int(seconds // 86400)
    return "yesterday" if days == 1 else f"{days}d ago"


@dataclass(frozen=True)
class Settings:
    """What a thread's next turn runs on, as keys and ids (render with the
    helpers above). ``conversation`` is the bound conversation, if any."""

    agent: str
    model: str | None
    cwd: str | None
    conversation: Any = None


async def settings_in_effect(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    conversation_thread_id: str,
    *,
    chat_kind: str,
    use_conversation: bool = True,
) -> Settings:
    """The agent, model and directory in effect for this thread.

    The bound conversation, when there is one, is the truth — it is what the
    next turn runs on. Without one (or with ``use_conversation=False``, for a
    group's defaults row) it is what a fresh conversation would open with: the
    thread's sticky settings, else the group's, else the channel's defaults
    (spec channels "Keep a chat's agent, model and directory across its conversations")."""
    threads = commands._threads
    row = await threads.get(binding.resource.uid, peer.chat_id, conversation_thread_id)
    if use_conversation and row is not None and row.active_conversation_id is not None:
        try:
            conv = await commands._conversations.get_conversation(row.active_conversation_id)
        except ConversationNotFound:
            conv = None
        if conv is not None:
            cfg = await commands._conversations.get_agent_config(row.active_conversation_id)
            cwd = cfg.cwd or default_cwd(binding)
            return Settings(conv.agent_key, cfg.model, cwd, conv)
    group = None
    if conversation_thread_id and chat_kind == "group":
        group = await threads.get(binding.resource.uid, peer.chat_id, "")

    def pick(field: str) -> str | None:
        return inherited_setting(row, group, field)

    agent = effective_agent(binding, pick("preferred_agent"))
    same = agent == pick("preferred_agent")
    defaults = binding.default_agent_config or {}
    model = pick("preferred_model") if same else None
    # The channel's default model belongs to its default agent only.
    channel_model = defaults.get("model") if agent == binding.default_agent else None
    return Settings(
        agent,
        model or channel_model,
        pick("preferred_cwd") or default_cwd(binding),
    )


def default_cwd(binding: ChannelBinding) -> str | None:
    """The channel's default working directory: where its new conversations start."""
    cwd = (binding.default_agent_config or {}).get("cwd")
    return str(cwd) if cwd else None


async def default_model_text(commands: ChannelCommands, agent: str) -> str:
    """``Default model (Opus 5.5)`` — the no-override choice, naming the model it
    resolves to when Coffer can know it, and plain ``Default model`` when it
    cannot (spec channels "Name the model the default resolves to")."""
    try:
        resolved = await commands._model_suggestions.resolved_default(agent)
    except Exception:
        resolved = None
    if not resolved:
        return "Default model"
    return f"Default model ({await _model_name(commands, agent, resolved)})"


async def _model_name(commands: ChannelCommands, agent: str, model: str) -> str:
    try:
        labels = await commands._model_suggestions.model_labels(agent)
    except Exception:
        labels = {}
    return labels.get(model) or model


async def model_display(commands: ChannelCommands, agent: str, model: str | None) -> str:
    """A model by the name its card button shows, else its id, else the default
    (with the model it resolves to, when known)."""
    if not model:
        return await default_model_text(commands, agent)
    return await _model_name(commands, agent, model)


async def settings_line(commands: ChannelCommands, settings: Settings) -> str:
    """``Claude Code · Opus 4.8 · ~/src/app`` — one line naming what a
    turn runs on: the agent, the model and the working directory.
    The `/new` card and `/status` both read it."""
    model = await model_display(commands, settings.agent, settings.model)
    parts = [agent_display(commands._agents, settings.agent), model]
    parts.append(dir_display(settings.cwd))
    return " · ".join(parts)
