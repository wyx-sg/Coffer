"""Channel routes (spec channels): pairing, status, notify, restart.

Channel CRUD rides the generic /resources endpoints; these are the
channel-specific operations from contracts/api.openapi.yaml. No route here is
called by an IM platform: Telegram is polled and SeaTalk pushes down an
outbound websocket connection the daemon holds.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from coffer.application.channel.credential_check import (
    CredentialCheck,
    CredentialCheckRequest,
)
from coffer.domain.channel.commands import COMMAND_ROSTER
from coffer.domain.channel.config import ChannelConfig
from coffer.domain.channel_type import ChannelType
from coffer.infrastructure.vault.home import content_root
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.channel_handoff import sdk_missing_handoff
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.handoff_schemas import HandoffOut, handoff_out

if TYPE_CHECKING:
    from coffer.application.channel.avatars import PersonAvatars
    from coffer.application.channel.service import ChannelService

router = APIRouter(prefix="/api/v1/channels", dependencies=[Depends(require_token)])

_SERVICE: Any = None
_CREDENTIAL_CHECK: CredentialCheck | None = None
_AVATARS: PersonAvatars | None = None


def set_channel_service(service: Any) -> None:
    global _SERVICE
    _SERVICE = service


def set_credential_check(check: CredentialCheck) -> None:
    global _CREDENTIAL_CHECK
    _CREDENTIAL_CHECK = check


def set_channel_avatars(avatars: PersonAvatars | None) -> None:
    global _AVATARS
    _AVATARS = avatars


def get_credential_check() -> CredentialCheck:
    if _CREDENTIAL_CHECK is None:
        raise RuntimeError("credential check not initialised")
    return _CREDENTIAL_CHECK


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


class ChannelPersonOut(BaseModel):
    """A person paired to the channel (spec channels "Gate inbound traffic on
    sender identity"): every one is answered with identical rights."""

    #: The person's stable platform identity — what a removal or a re-pair names.
    sender_id: str
    display_name: str
    #: When this person was first paired.
    paired_at: datetime
    #: Their direct chat.
    chat_id: str
    active_conversation_id: str | None


class PairingCodeIn(BaseModel):
    #: The paired person whose identity the claimant takes over (re-pair).
    #: Omitted, the claimant is added beside everyone already paired.
    replaces: str | None = None


class InboundInfoOut(BaseModel):
    """A SeaTalk channel's websocket connection — the one road its events take.

    Spec channels/seatalk "Report the websocket connection as the channel's
    inbound state". There is no listener, port, path, public URL or tunnel to
    report, so the connection state is the whole health answer.
    """

    #: ``rejected`` is SeaTalk refusing the app's credentials at register;
    #: ``error`` any other failed attempt (DNS, a timeout, a dropped socket).
    websocket_state: (
        Literal["connecting", "connected", "kicked", "sdk_missing", "rejected", "error"] | None
    )
    websocket_error: str | None


class ChannelDiagnosticOut(BaseModel):
    code: str
    message: str


class SecretApprovalOut(BaseModel):
    """Why a channel's adapter is not running when its secret is the cause.

    ``pending`` waits for the owner's approval in the Coffer app; ``refused``
    was declined and stays so until asked again from the Secrets page. Names the
    secret by ref, never carries its value.
    """

    state: Literal["pending", "refused"]
    secret_ref: str


class ChannelCommandOut(BaseModel):
    """One slash command the channel answers (spec channels "Answer the
    conversation commands from any paired chat"), from the one roster that also
    feeds the help text and the platform menus."""

    #: Without the leading slash.
    name: str
    #: A short argument hint (`[agent]`), or "".
    args: str
    description: str
    description_zh: str


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
    #: Everyone paired to the channel, earliest first. Empty: not paired yet.
    people: list[ChannelPersonOut]
    #: A SeaTalk channel's websocket connection; null for telegram, whose
    #: inbound is the adapter's own polling and is reported by ``running``.
    inbound: InboundInfoOut | None
    diagnostics: list[ChannelDiagnosticOut] = []
    #: Set while the channel's secret waits for the owner's approval (or was
    #: refused): the real reason behind ``running: false``. ``null`` otherwise.
    secret_approval: SecretApprovalOut | None = None
    #: Enabled for this machine and not running only because the daemon has not
    #: reached it yet — it starts within one reconcile tick. ``running: false``
    #: with this set is "starting", never a failed start (spec channels "Report
    #: a channel that is starting apart from one that failed to start").
    starting: bool = False
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
    #: "Manage channels from the Channels page"): the one typed reading
    #: of its configuration, so a surface never carries a copy of the defaults.
    #: ``null`` only for a stored configuration that no longer validates.
    settings: ChannelConfig | None = None
    #: Every command the channel answers, in the roster's order — the Overview
    #: lists them so nobody has to type /help to learn them.
    commands: list[ChannelCommandOut] = []
    #: Coffer's workspace: where a new conversation starts when the channel
    #: marks no default directory, so the Settings tab can show it as the
    #: default from the start.
    workspace_directory: str = ""


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


class ValidateCredentialsIn(BaseModel):
    """Credentials to check, as typed. Which fields apply depends on the platform."""

    platform: ChannelType
    bot_token: str | None = Field(default=None, max_length=512)
    app_id: str | None = Field(default=None, max_length=128)
    app_secret: str | None = Field(default=None, max_length=512)
    #: An existing channel to compare with: answers "is this the same bot?", and
    #: supplies the app id when a SeaTalk replacement does not repeat it.
    channel_uid: str | None = None


class CredentialCheckOut(BaseModel):
    ok: bool
    #: Without the at-sign; null where the platform has none (SeaTalk).
    bot_handle: str | None
    bot_name: str | None
    #: Whether the credentials are the named channel's own bot; null when there
    #: was nothing to compare with.
    same_bot: bool | None
    #: Why not ok: the platform said no (``rejected``), could not be asked
    #: (``unreachable``, ``timeout``), or a needed field is empty (``missing``).
    reason: Literal["missing", "rejected", "unreachable", "timeout"] | None
    #: The platform's own words about a rejection, when it gave any.
    detail: str | None


@router.post("/validate-credentials", response_model=CredentialCheckOut)
async def validate_credentials(body: ValidateCredentialsIn) -> CredentialCheckOut:
    """Check credentials against the platform without storing anything (spec
    channels "Check credentials before they are saved"). A refusal is a normal
    answer (``ok: false`` with a reason), not an error response."""
    result = await get_credential_check().check(
        CredentialCheckRequest(
            platform=body.platform,
            bot_token=body.bot_token,
            app_id=body.app_id,
            app_secret=body.app_secret,
            channel_uid=body.channel_uid,
        )
    )
    return CredentialCheckOut(
        ok=result.ok,
        bot_handle=result.bot_handle,
        bot_name=result.bot_name,
        same_bot=result.same_bot,
        reason=result.reason,
        detail=result.detail,
    )


@router.post("/{uid}/pairing-code", response_model=PairingCodeOut)
async def issue_pairing_code(
    uid: str, body: PairingCodeIn | None = None, actor: str = Depends(get_actor)
) -> PairingCodeOut:
    code, expires_at, pair_url = await get_channel_service().issue_pairing_code(
        uid, actor=actor, replaces=body.replaces if body else None
    )
    return PairingCodeOut(code=code, expires_at=expires_at, pair_url=pair_url)


@router.delete("/{uid}/pairing-code", status_code=204, response_class=Response)
async def cancel_pairing_code(uid: str) -> None:
    await get_channel_service().cancel_pairing_code(uid)


@router.delete("/{uid}/people/{sender_id}", status_code=204, response_class=Response)
async def remove_person(uid: str, sender_id: str, actor: str = Depends(get_actor)) -> None:
    await get_channel_service().remove_person(uid, sender_id, actor=actor)
    if _AVATARS is not None:
        _AVATARS.forget(uid, sender_id)


@router.get(
    "/{uid}/people/{sender_id}/avatar",
    response_class=Response,
    responses={
        200: {
            "content": {"image/*": {"schema": {"type": "string", "format": "binary"}}},
            "description": "The person's picture on the platform.",
        },
        204: {"description": "No picture: show the person's initials."},
    },
)
async def person_avatar(uid: str, sender_id: str) -> Response:
    """spec channels "Show each paired person's platform picture": the picture,
    or 204 when there is none to show (not paired, none on the platform, the
    platform refused, or the channel does not run here)."""
    avatar = await _AVATARS.get(uid, sender_id) if _AVATARS is not None else None
    if avatar is None:
        return Response(status_code=204)
    return Response(
        content=avatar.data,
        media_type=avatar.content_type,
        # Private to this user; the page re-reads it when the list does.
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{uid}/status", response_model=ChannelStatusOut)
async def channel_status(uid: str) -> ChannelStatusOut:
    status = await get_channel_service().status(uid)
    people = [
        ChannelPersonOut(
            sender_id=p.sender_id,
            display_name=p.display_name,
            paired_at=p.paired_at,
            chat_id=p.chat_id,
            active_conversation_id=p.active_conversation_id,
        )
        for p in status.people
    ]
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
        people=people,
        inbound=inbound,
        diagnostics=[
            ChannelDiagnosticOut(code=d.code, message=d.message) for d in status.diagnostics
        ],
        secret_approval=(
            SecretApprovalOut(
                state=status.secret_approval.state,  # type: ignore[arg-type]
                secret_ref=status.secret_approval.secret_ref,
            )
            if status.secret_approval is not None
            else None
        ),
        starting=status.starting,
        settings=status.settings,
        workspace_directory=str(content_root() / "workspace"),
        commands=[
            ChannelCommandOut(
                name=c.name,
                args=c.args,
                description=c.description,
                description_zh=c.description_zh,
            )
            for c in COMMAND_ROSTER
        ],
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
