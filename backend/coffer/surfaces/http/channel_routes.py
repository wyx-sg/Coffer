"""Channel routes (spec channels): pairing, status, notify, restart.

Channel CRUD rides the generic /resources endpoints; these are the
channel-specific operations from contracts/api.openapi.yaml. No route here is
called by an IM platform: Telegram is polled and SeaTalk pushes down an
outbound websocket connection the daemon holds.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.domain.channel.config import ChannelConfig
from coffer.domain.channel_type import ChannelType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.channel_handoff import sdk_missing_handoff
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.handoff_schemas import HandoffOut, handoff_out

if TYPE_CHECKING:
    from coffer.application.channel.service import ChannelService

router = APIRouter(prefix="/api/v1/channels", dependencies=[Depends(require_token)])

_SERVICE: Any = None


def set_channel_service(service: Any) -> None:
    global _SERVICE
    _SERVICE = service


def get_channel_service() -> ChannelService:
    if _SERVICE is None:
        raise RuntimeError("channel service not initialised")
    return _SERVICE  # type: ignore[no-any-return]


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime
    # "Pair by a one-tap start link": a link that carries the code, so the
    # owner pairs by opening it.
    # "" when the platform has no such link or the bot's username is unknown —
    # the typed code always works.
    pair_url: str = ""


class ChannelPeerOut(BaseModel):
    chat_id: str
    display_name: str
    paired_at: datetime
    active_conversation_id: str | None


class InboundInfoOut(BaseModel):
    """A SeaTalk channel's websocket connection — the one road its events take.

    Spec channels/seatalk "Report the websocket connection as the channel's
    inbound state". There is no listener, port, path, public URL or tunnel to
    report, so the connection state is the whole health answer.
    """

    websocket_state: Literal["connecting", "connected", "kicked", "sdk_missing", "error"] | None
    websocket_error: str | None


class ChannelDiagnosticOut(BaseModel):
    code: str
    message: str


class ChannelStatusOut(BaseModel):
    #: The channel's identity — what every route addresses.
    uid: str
    #: A mutable label. It is what the page, the CLI and every error message
    #: about this channel show, because a uid in front of a person is a dead end.
    name: str
    channel_type: ChannelType
    enabled: bool
    running: bool
    pending_pairing: bool
    peer: ChannelPeerOut | None
    #: A SeaTalk channel's websocket connection; null for telegram, whose
    #: inbound is the adapter's own polling and is reported by ``running``.
    inbound: InboundInfoOut | None
    diagnostics: list[ChannelDiagnosticOut] = []
    # The machine whose daemon runs this channel's adapter (spec channels
    # "Bind each channel to the one machine that runs it"), and whether that machine is the one
    # answering this request. Both travel, because ``running: false`` is two
    # different facts — a channel that failed to start here, and a channel that
    # was never this machine's to start — and a surface cannot tell them apart
    # from a single boolean. ``runs_on`` is the raw machine id; the name beside
    # it comes from `GET /sync/machines`, which is where the registry lives.
    runs_on: str | None = None
    runs_here: bool = False
    #: The display title a person chose (spec resource-framework "Carry an optional
    #: editable title on the kinds that have one"); ``None`` when unset, and a surface shows
    #: the name in its place.
    title: str | None = None
    #: While the websocket reports ``sdk_missing``: the prompt that has the
    #: person's agent put SeaTalk's SDK where the daemon loads it from (spec
    #: channels/seatalk "Load the websocket client library from an
    #: operator-supplied directory"). ``None`` in every other state.
    handoff: HandoffOut | None = None
    #: The channel's settings with every default filled in (spec channels
    #: "Manage channels from the Channels page and the CLI"): the one typed reading
    #: of its configuration, so a surface never carries a copy of the defaults.
    #: ``null`` only for a stored configuration that no longer validates.
    settings: ChannelConfig | None = None


class NotifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    #: Which paired chat to push to. Omitted, the channel's owner chat (its
    #: earliest pairing — the owner's DM). A chat this channel is not paired to
    #: is refused, so a caller cannot address an arbitrary group.
    chat_id: str | None = None


class NotifyOut(BaseModel):
    sent: bool


class RestartOut(BaseModel):
    #: Whether the channel's adapter is running once the restart has finished.
    running: bool


@router.post("/{uid}/pairing-code", response_model=PairingCodeOut)
async def issue_pairing_code(uid: str, actor: str = Depends(get_actor)) -> PairingCodeOut:
    code, expires_at, pair_url = await get_channel_service().issue_pairing_code(uid, actor=actor)
    return PairingCodeOut(code=code, expires_at=expires_at, pair_url=pair_url)


@router.get("/{uid}/status", response_model=ChannelStatusOut)
async def channel_status(uid: str) -> ChannelStatusOut:
    status = await get_channel_service().status(uid)
    peer = (
        ChannelPeerOut(
            chat_id=status.peer.chat_id,
            display_name=status.peer.display_name,
            paired_at=status.peer.paired_at,
            active_conversation_id=status.peer_conversation_id,
        )
        if status.peer is not None
        else None
    )
    inbound = (
        InboundInfoOut(
            websocket_state=status.inbound.websocket_state,  # type: ignore[arg-type]
            websocket_error=status.inbound.websocket_error,
        )
        if status.inbound is not None
        else None
    )
    return ChannelStatusOut(
        uid=status.uid,
        name=status.name,
        title=status.title,
        channel_type=status.channel_type,  # type: ignore[arg-type]
        enabled=status.enabled,
        running=status.running,
        pending_pairing=status.pending_pairing,
        peer=peer,
        inbound=inbound,
        diagnostics=[
            ChannelDiagnosticOut(code=d.code, message=d.message) for d in status.diagnostics
        ],
        runs_on=status.runs_on,
        runs_here=status.runs_here,
        settings=status.settings,
        handoff=handoff_out(
            sdk_missing_handoff(status.name)
            if inbound is not None and inbound.websocket_state == "sdk_missing"
            else None
        ),
    )


@router.post("/{uid}/notify", response_model=NotifyOut)
async def notify_channel(uid: str, body: NotifyIn, actor: str = Depends(get_actor)) -> NotifyOut:
    await get_channel_service().notify(uid, body.text, actor=actor, chat_id=body.chat_id)
    return NotifyOut(sent=True)


@router.post("/{uid}/restart", response_model=RestartOut)
async def restart_channel(uid: str) -> RestartOut:
    """Stop and rebuild the channel's adapter, reading its secret afresh."""
    return RestartOut(running=await get_channel_service().restart(uid))
