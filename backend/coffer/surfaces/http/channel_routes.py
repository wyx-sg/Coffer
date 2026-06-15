"""Channel routes (spec 009): pairing, status, notify, event ingest.

Channel CRUD rides the generic /resources endpoints; these are the
channel-specific operations from contracts/api.openapi.yaml.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

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


class ChannelPeerOut(BaseModel):
    chat_id: str
    display_name: str
    paired_at: datetime
    active_conversation_id: str | None


class CallbackInfoOut(BaseModel):
    port: int
    path: str
    listener_running: bool
    public_base_url: str | None = None
    public_callback_url: str | None = None


class CallbackTestOut(BaseModel):
    ok: bool
    detail: str


class ChannelStatusOut(BaseModel):
    name: str
    channel_type: str
    enabled: bool
    running: bool
    pending_pairing: bool
    peer: ChannelPeerOut | None
    callback: CallbackInfoOut | None


class NotifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class NotifyOut(BaseModel):
    sent: bool


class EventAcceptedOut(BaseModel):
    accepted: bool


@router.post("/{name}/pairing-code", response_model=PairingCodeOut)
async def issue_pairing_code(name: str, actor: str = Depends(get_actor)) -> PairingCodeOut:
    code, expires_at = await get_channel_service().issue_pairing_code(name, actor=actor)
    return PairingCodeOut(code=code, expires_at=expires_at)


@router.get("/{name}/status", response_model=ChannelStatusOut)
async def channel_status(name: str) -> ChannelStatusOut:
    status = await get_channel_service().status(name)
    peer = (
        ChannelPeerOut(
            chat_id=status.peer.chat_id,
            display_name=status.peer.display_name,
            paired_at=status.peer.paired_at,
            active_conversation_id=status.peer.active_conversation_id,
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
        )
        if status.callback is not None
        else None
    )
    return ChannelStatusOut(
        name=status.name,
        channel_type=status.channel_type,
        enabled=status.enabled,
        running=status.running,
        pending_pairing=status.pending_pairing,
        peer=peer,
        callback=callback,
    )


@router.post("/{name}/notify", response_model=NotifyOut)
async def notify_channel(name: str, body: NotifyIn, actor: str = Depends(get_actor)) -> NotifyOut:
    await get_channel_service().notify(name, body.text, actor=actor)
    return NotifyOut(sent=True)


@router.post("/{name}/callback-test", response_model=CallbackTestOut)
async def test_channel_callback(name: str) -> CallbackTestOut:
    """Probe a SeaTalk channel's public callback URL end to end."""
    result = await get_channel_service().test_callback(name)
    return CallbackTestOut(ok=result.ok, detail=result.detail)


@router.post("/{name}/events", response_model=EventAcceptedOut)
async def ingest_channel_event(name: str, envelope: dict[str, Any]) -> EventAcceptedOut:
    """Verified SeaTalk events forwarded by the callback listener."""
    await get_channel_service().ingest_event(name, envelope)
    return EventAcceptedOut(accepted=True)
