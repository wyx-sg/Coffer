"""Shared helpers for the live agent adapters (spec chat).

Small, dependency-free pieces the SDK-backed (:mod:`claude_sdk_agent`) and
app-server-backed (:mod:`codex_agent`) adapters both need:

- :class:`ParseState` — mutable state threaded through a turn's output parsing
  (the discovered session id, in-flight tool names, token counts, and whether a
  terminal event has been emitted yet).
- :data:`SessionSink` — the callback an adapter calls to persist a newly
  discovered upstream session id back onto the conversation, so the next turn
  can ``--resume`` it.
- :func:`last_user_text` — the prompt for a turn: the text of the most recent
  user message in the history.
- :func:`channel_system_context` — the append telling a channel-driven agent it
  is on a phone chat rather than at a terminal.
- :func:`model_system_context` — the append naming the model Coffer put the
  session on, and what else it could be switched to.
- :func:`compose_system_context` — the three appends a provider owes its agent
  (channel, model, memory digest), joined into the one string it passes on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from coffer.domain.chat.message import Message, Role, TextBlock

#: Persist a discovered upstream session id back onto the conversation.
SessionSink = Callable[[str], Awaitable[None]]


@dataclass
class ParseState:
    """Mutable state threaded through an adapter's per-turn output parsing."""

    session_id: str | None = None
    tool_names: dict[str, str] = field(default_factory=dict)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False


def last_user_text(history: Sequence[Message]) -> str:
    """The text of the most recent user message — the prompt for this turn."""
    for msg in reversed(history):
        if msg.role is Role.USER:
            return "".join(b.text for b in msg.content if isinstance(b, TextBlock)).strip()
    return ""


def channel_system_context(channel_name: str | None) -> str:
    """A system-prompt append telling a channel-driven agent where it is.

    Without it the agent has no idea it is bridged to a phone chat: it dumps
    terminal-sized replies, waits on OS permission dialogs nobody can click, and
    reinvents ways to reach the user. Kept short — it rides on every channel turn.

    ``channel_name`` is a label resolved from the conversation's stored channel
    uid, so it can come back ``None`` — the channel was deleted while a thread
    still pointed at it. The name is only colour here; every instruction below
    it holds regardless. So an unresolvable name drops the name and keeps the
    append, rather than leaving a channel turn with no channel context at all.
    """
    where = f"the {channel_name} chat channel" if channel_name else "a chat channel"
    return (
        f"You are talking with the user over {where} — "
        "most likely on their phone, not at a terminal. Keep replies short and "
        "easy to read on a small screen: lead with the answer, and skip large "
        "tables or long code dumps unless asked. You cannot click permission or "
        "confirmation dialogs on the user's computer, and they may be away from "
        "it — if something needs a click or an OS permission, say so and do what "
        "you can instead of waiting on it. To send the user a file or image, put "
        "it on its own line as `MEDIA:/absolute/path` (optionally "
        "`MEDIA:/absolute/path | a caption`). The file must exist on this machine; "
        "the channel uploads it — an image by extension is sent as a photo, "
        "otherwise as a document — and removes the line from your reply. Ordinary "
        "prose and markdown image links are never sent, so use this sentinel only "
        "for files you actually want to deliver."
    )


#: How many ids the per-turn model note names before deferring to the picker.
#: Discovery leads with the newest releases, so the head of the list is the part
#: worth spending prompt on.
_MODELS_IN_NOTE = 12


def model_system_context(current: str | None, available: Sequence[str]) -> str:
    """A system-prompt append telling the agent which model Coffer put it on.

    The agent cannot see Coffer's choice — asked in a real channel session it
    confidently named the wrong model. This note is authoritative, so it says so.
    It rides on every turn, hence the tight wording.
    """
    # The catalogue is now read from the CLI itself and runs to ~20 ids. All of
    # them on every turn is prompt weight the agent gains nothing from — it only
    # needs enough to answer "what could I be switched to", so name the leading
    # few and point at the picker for the rest.
    shown = list(available[:_MODELS_IN_NOTE])
    rest = len(available) - len(shown)
    ids = ", ".join(shown) if shown else "none listed"
    if rest > 0:
        ids += f" (+{rest} more in Coffer's picker)"
    if current:
        opening = (
            f"Coffer is running this session on the model `{current}` — trust this "
            "note over your own guess about which model you are."
        )
    else:
        opening = (
            "Coffer set no model override for this session, so you are running on "
            "your CLI's own default model. Trust this note over your own guess: do "
            "not name a specific model or version, say the default is in use."
        )
    return (
        f"{opening} Models available here: {ids}. The user switches with "
        "`/model <id>` in a chat channel, or Coffer's model picker in the web UI — "
        "point them there instead of changing models yourself."
    )


__all__ = [
    "ParseState",
    "SessionSink",
    "channel_system_context",
    "last_user_text",
    "model_system_context",
]


#: Resolves the models an agent could be switched to, for the per-turn note.
ModelLister = Callable[[str], Awaitable[Sequence[str]]]
#: (agent_key, cwd) -> the memory digest for this turn, or None (spec memory
#: "Deliver to channel turns through the system prompt").
MemoryContextComposer = Callable[[str, str], Awaitable[str | None]]
#: channel uid -> the channel's current name, or None when no channel carries
#: that uid any more. A conversation stores the uid of the channel it is bridged
#: to (ADR resource-identity-is-an-immutable-uid); the system prompt wants the
#: label a human would use. This callable is the one place the two meet — a
#: narrow seam rather than a ``ResourceService`` dependency, so this layer keeps
#: reading one field out of the registry instead of importing it.
ChannelNameResolver = Callable[[str], Awaitable[str | None]]
#: () -> the environment overrides that point the agent's runtime at the config
#: directory of the agent answering for this provider's type —
#: ``{"CLAUDE_CONFIG_DIR": dir}`` / ``{"CODEX_HOME": dir}`` for a custom one,
#: ``{}`` for the default (spec chat "Ship Claude Code and Codex subprocess
#: providers"). A narrow seam so chat never imports the agent kind; the
#: composition root builds it over the agent registry.
HomeEnvResolver = Callable[[], Awaitable[dict[str, str]]]


async def compose_system_context(
    *,
    agent_key: str,
    channel_uid: str,
    cwd: str,
    model: str | None,
    list_models: ModelLister | None,
    compose_memory: MemoryContextComposer | None,
    resolve_channel_name: ChannelNameResolver | None = None,
) -> str:
    """The appends every provider owes its agent, joined into one.

    Three of them, and the order is the order they matter in:

    * a channel-originated conversation drives the agent from a phone chat, so
      tell it so — concise replies, no clickable dialogs;
    * a channel-driven turn also carries the memory digest (spec memory "Deliver to
      channel turns through the system prompt"): Coffer composes this turn's
      context itself, so memory reaches the agent with no session-start hook and
      no install. **Only** a channel turn gets it — an agent the developer
      drives themselves receives memory through its own hook (spec memory
      "Install delivery hooks explicitly and removably"), never both;
    * every conversation gets the model note, because the agent cannot see
      which model Coffer put it on and otherwise invents an answer.

    Shared rather than written twice because both providers owe the same
    thing: Codex went without any of it until this was extracted, which is
    exactly the drift a second copy invites.

    ``channel_uid`` is what the conversation stores, and ``resolve_channel_name``
    turns it into the label the prompt reads. They are kept apart on purpose:
    the uid answers "is this a channel turn, and which channel", which has to
    stay true across a rename, and the name answers "what does the user call
    it", which is only ever read here and now.
    """
    parts: list[str] = []
    # Whether this is a channel turn is decided by the stored uid, never by
    # whether its label could be resolved. A deleted channel would otherwise
    # silently downgrade a phone-chat turn to a terminal one — dropping the
    # "keep it short, you cannot click dialogs" contract and the memory digest
    # with it — for the one reason least related to where the user is sitting.
    if channel_uid:
        channel_name = (
            await resolve_channel_name(channel_uid) if resolve_channel_name is not None else None
        )
        parts.append(channel_system_context(channel_name))
        if compose_memory is not None:
            memory = await compose_memory(agent_key, cwd)
            if memory:
                parts.append(memory)
    available = await list_models(agent_key) if list_models else []
    parts.append(model_system_context(model, available))
    return "\n\n".join(parts)
