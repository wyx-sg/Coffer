"""Channel routes (spec channels): pairing, status, notify, event ingest.

Channel CRUD rides the generic /resources endpoints; these are the
channel-specific operations from contracts/api.openapi.yaml.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor

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
    # FR-051: a link that carries the code, so the owner pairs by opening it.
    # "" when the platform has no such link or the bot's username is unknown —
    # the typed code always works.
    pair_url: str = ""


class ChannelPeerOut(BaseModel):
    chat_id: str
    display_name: str
    paired_at: datetime
    active_conversation_id: str | None


class CallbackInfoOut(BaseModel):
    """How a SeaTalk channel receives events (spec channels/seatalk FR-004).

    Covers both delivery methods. On ``websocket`` the webhook-only fields report
    their absent/false values — there is no port, path, public URL, listener or
    tunnel on that path — and ``websocket_state`` carries the health answer.
    """

    port: int
    path: str
    listener_running: bool
    delivery: Literal["webhook", "websocket"] = "webhook"
    public_base_url: str | None = None
    public_callback_url: str | None = None
    tunnel_managed: bool = False
    tunnel_running: bool = False
    websocket_state: Literal["connecting", "connected", "kicked", "sdk_missing", "error"] | None = (
        None
    )
    websocket_error: str | None = None


class CallbackTestOut(BaseModel):
    ok: bool
    detail: str


class ChannelDiagnosticOut(BaseModel):
    code: str
    message: str


class ChannelStatusOut(BaseModel):
    #: The channel's identity — what every route addresses and what the public
    #: callback path is keyed by.
    uid: str
    #: A mutable label. It is what the page, the CLI and every error message
    #: about this channel show, because a uid in front of a person is a dead end.
    name: str
    channel_type: str
    enabled: bool
    running: bool
    pending_pairing: bool
    peer: ChannelPeerOut | None
    callback: CallbackInfoOut | None
    diagnostics: list[ChannelDiagnosticOut] = []
    # The machine whose daemon runs this channel's adapter (spec channels
    # ``## Where a channel runs``), and whether that machine is the one
    # answering this request. Both travel, because ``running: false`` is two
    # different facts — a channel that failed to start here, and a channel that
    # was never this machine's to start — and a surface cannot tell them apart
    # from a single boolean. ``runs_on`` is the raw machine id; the name beside
    # it comes from `GET /sync/machines`, which is where the registry lives.
    runs_on: str | None = None
    runs_here: bool = False


class NotifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    #: Which paired chat to push to. Omitted, the channel's owner chat (its
    #: earliest pairing — the owner's DM). A chat this channel is not paired to
    #: is refused, so a caller cannot address an arbitrary group.
    chat_id: str | None = None


class NotifyOut(BaseModel):
    sent: bool


class EventAcceptedOut(BaseModel):
    accepted: bool


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
    callback = (
        CallbackInfoOut(
            port=status.callback.port,
            path=status.callback.path,
            listener_running=status.callback.listener_running,
            public_base_url=status.callback.public_base_url,
            public_callback_url=status.callback.public_callback_url,
            tunnel_managed=status.callback.tunnel_managed,
            tunnel_running=status.callback.tunnel_running,
            delivery=status.callback.delivery,  # type: ignore[arg-type]
            websocket_state=status.callback.websocket_state,  # type: ignore[arg-type]
            websocket_error=status.callback.websocket_error,
        )
        if status.callback is not None
        else None
    )
    return ChannelStatusOut(
        uid=status.uid,
        name=status.name,
        channel_type=status.channel_type,
        enabled=status.enabled,
        running=status.running,
        pending_pairing=status.pending_pairing,
        peer=peer,
        callback=callback,
        diagnostics=[
            ChannelDiagnosticOut(code=d.code, message=d.message) for d in status.diagnostics
        ],
        runs_on=status.runs_on,
        runs_here=status.runs_here,
    )


@router.post("/{uid}/notify", response_model=NotifyOut)
async def notify_channel(uid: str, body: NotifyIn, actor: str = Depends(get_actor)) -> NotifyOut:
    await get_channel_service().notify(uid, body.text, actor=actor, chat_id=body.chat_id)
    return NotifyOut(sent=True)


@router.post("/{uid}/callback-test", response_model=CallbackTestOut)
async def test_channel_callback(uid: str) -> CallbackTestOut:
    """Probe a SeaTalk channel's public callback URL end to end."""
    result = await get_channel_service().test_callback(uid)
    return CallbackTestOut(ok=result.ok, detail=result.detail)


@router.post("/{uid}/events", response_model=EventAcceptedOut)
async def ingest_channel_event(uid: str, envelope: dict[str, Any]) -> EventAcceptedOut:
    """Verified SeaTalk events forwarded by the callback listener.

    The listener addresses this by uid because the public callback path it
    serves is itself keyed by uid — that URL is registered by hand on SeaTalk's
    platform, so it is the last place a mutable label belongs."""
    await get_channel_service().ingest_event(uid, envelope)
    return EventAcceptedOut(accepted=True)
