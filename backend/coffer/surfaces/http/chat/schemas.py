"""Pydantic schemas for the chat routes.

Every request/response body the Conversations page's REST surface serves is
modelled here; the chat contract is generated from them (``make contracts``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from coffer.domain.channel_type import ChannelType

# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class ConversationPatch(BaseModel):
    """Body for PATCH /conversations/{id}."""

    title: str | None = None


class ChannelPlaceOut(BaseModel):
    """Where in its channel a conversation lives — what the Conversations list's
    source badge names ("SeaTalk · DM · 🧵#2", "SeaTalk · <group> > thread")."""

    #: ``direct`` (a DM) or ``group``; null when the channel never said.
    chat_kind: Literal["direct", "group"] | None = None
    #: The conversation lives in a thread or topic, not the chat's main timeline.
    thread: bool = False
    #: The ``🧵#N title`` mark of a ``/thread`` parallel conversation.
    parallel_mark: str | None = None
    #: The group's display name, when Coffer knows one.
    chat_name: str | None = None


class ChannelBindingOut(BaseModel):
    """The IM channel a conversation is driven from.

    The return address for relaying the agent's output back to the channel;
    present on every conversation Coffer lists.
    """

    #: The channel's identity — what a client follows to reach the channel.
    channel_uid: str
    #: The channel's label, resolved at read time. None when the channel has
    #: since been deleted: the conversation keeps its binding (it really did
    #: come from a channel), but there is no longer a name to show for it.
    channel: str | None
    chat_id: str
    #: The channel's type key (``seatalk`` / ``telegram``); null when the
    #: channel has since been deleted.
    platform: ChannelType | None = None
    #: Which chat and thread of the channel the conversation lives in; null
    #: when that is not known.
    place: ChannelPlaceOut | None = None


class ConversationOut(BaseModel):
    """Single conversation response."""

    id: str
    agent_key: str
    title: str
    created_at: datetime
    updated_at: datetime
    #: The channel the conversation is driven from.
    channel_binding: ChannelBindingOut | None = None
    #: The directory the agent's session works in; null until a turn set it.
    cwd: str | None = None
    #: The agent's own session id, once a turn ran; null before.
    session_id: str | None = None
    #: A turn is in flight right now.
    running: bool = False
    #: A question the agent asked is waiting for the owner's answer (spec chat
    #: "Show which conversations wait on you").
    needs_you: bool = False
