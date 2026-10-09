"""ChannelService — pairing codes, status, notify, event ingest.

The REST routes and CLI talk to this; adapter lifecycle belongs to
ChannelRuntime and message flow to InboundProcessor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.channel.inbound_status import InboundInfo, inbound_info
from coffer.application.channel.pairing import PairingManager, start_link
from coffer.application.channel.people import ChannelPerson, people_of
from coffer.application.channel.ports import EventIngestAdapter
from coffer.application.channel.store_ports import (
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.channel.config import (
    SeaTalkChannelConfig,
    TelegramChannelConfig,
    parse_channel_config,
)
from coffer.domain.channel.errors import (
    ChannelNotPaired,
    ChannelNotRunning,
    ChannelPersonNotFound,
)
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.channel.runtime import ChannelRuntime
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelDiagnostic:
    """Something about the channel that looks configured but will not work.

    spec channels "Diagnose configuration a platform setting defeats": the failure mode
    this exists for is a setting that reads correctly in Coffer and does nothing in the
    chat. A diagnostic always names the fix — reporting a problem the user cannot act on
    is just noise.
    """

    code: str  # stable identifier, so the UI can style or link it
    message: str  # what is wrong and what to do about it


@dataclass(frozen=True)
class SecretApproval:
    """The channel's secret is the reason its adapter is not running.

    ``pending`` waits for the owner's approval in the Coffer app; ``refused`` was
    declined and stays so until the owner asks again (the channel banner's Ask again).
    ``secret_ref`` names the secret (never its value).
    """

    state: str
    secret_ref: str


@dataclass(frozen=True)
class ChannelStatus:
    #: The channel's identity — what a surface addresses it by and builds links
    #: from. Beside the name rather than instead of it: this object is rendered
    #: on a page a person reads, and the two answer different questions.
    uid: str
    name: str
    channel_type: str
    enabled: bool
    running: bool
    pending_pairing: bool
    #: Everyone paired to the channel, earliest first; each carries the
    #: conversation their direct chat is driving.
    people: tuple[ChannelPerson, ...]
    # A SeaTalk channel's websocket connection; None for telegram, whose
    # inbound is the adapter's own polling and is reported by ``running``.
    inbound: InboundInfo | None
    # spec channels "Diagnose configuration a platform setting defeats": contradictions
    # between the configuration and what the platform actually permits. Empty is the
    # healthy case.
    diagnostics: tuple[ChannelDiagnostic, ...] = ()
    # Set while the channel's secret waits for (or was refused) the owner's
    # approval — the cause behind ``running: false`` that no websocket state
    # explains (spec channels "Report a channel whose secret waits for approval").
    secret_approval: SecretApproval | None = None
    # The machine this channel is bound to, and whether that machine is this
    # one (spec channels "Bind each channel to the one machine that runs it").
    # Both, because ``running`` alone cannot tell "stopped" from "not mine to
    # start", and those two need opposite reactions from the user: one is a
    # fault to chase, the other is the system working. ``runs_on`` is the raw
    # id — resolving it to a machine NAME needs the registry, which lives in the
    # sync module's working tree, so the surface that has it does the resolving
    # and the CLI prints the id.
    runs_on: str | None = None
    runs_here: bool = False
    #: Enabled here and not yet reached by the reconciler (``start_pending``).
    starting: bool = False
    #: The display title a person chose (spec resource-framework "Carry an optional
    #: editable title on the kinds that have one"); ``None`` when unset, and a surface shows
    #: the name in its place.
    title: str | None = None
    #: The channel's settings with every default filled in — the typed reading of
    #: its stored configuration. ``None`` for a stored configuration that no longer
    #: validates, which the surfaces report as a fault rather than guess at.
    settings: TelegramChannelConfig | SeaTalkChannelConfig | None = None


class ChannelService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        peers: ChannelPeerRepoPort,
        threads: ChannelThreadConversationRepoPort,
        pairing: PairingManager,
        runtime: ChannelRuntime,
        audit: AuditService,
    ) -> None:
        self._resources = resources
        self._peers = peers
        self._threads = threads
        self._pairing = pairing
        self._runtime = runtime
        self._audit = audit

    async def _channel(self, channel_uid: str) -> Resource:
        """The channel row, by its identity.

        Every method here addresses a channel by ``uid`` (ADR
        identity-is-the-uid-inside-the-file). A name reaches Coffer only where
        a person typed one — the CLI resolves it and the web UI never had it —
        and a service that accepted both would be the round trip this change
        exists to delete: the route resolving uid → name so that the service can
        resolve name → row. Whatever needs the label past this line reads it off
        the row.
        """
        return await self._resources.get(channel_uid)

    async def issue_pairing_code(
        self, channel_uid: str, *, actor: str, replaces: str | None = None
    ) -> tuple[str, datetime, str]:
        """Generate a pairing code for the channel (replacing any pending one).

        The person who claims it is added beside the ones already paired; with
        ``replaces`` (a paired person's ``sender_id``) they take that person's
        place instead (spec channels "Gate inbound traffic on sender identity").

        Returns the code, its expiry, and — where the platform has a
        parameterised start link and the bot's username is known — a link that
        carries the code (see "Pair by a one-tap start link"), so the owner
        pairs by opening it instead of transcribing eight characters on a phone.
        The link is "" when there is none; the typed code always works.
        """
        resource = await self._channel(channel_uid)
        if replaces is not None:
            await self._person(resource, replaces)
        # Pending code and running adapter are both keyed by the channel's uid, so
        # a rename between issuing and claiming keeps both.
        code, expires_at = self._pairing.issue(resource.uid, replaces=replaces)
        details = {"expires_at": expires_at.isoformat()}
        if replaces is not None:
            details["replaces"] = replaces
        await self._audit.record(
            AuditEventType.CHANNEL_PAIRING_ISSUED.value,
            resource=resource,
            actor=actor,
            details=details,
        )
        return code, expires_at, self._pair_link(resource.uid, code)

    async def _person(self, resource: Resource, sender_id: str) -> ChannelPerson:
        people = people_of(await self._peers.list_by_resource(resource.uid))
        for person in people:
            if person.sender_id == sender_id:
                return person
        raise ChannelPersonNotFound(resource.name, sender_id)

    async def cancel_pairing_code(self, channel_uid: str) -> None:
        """Drop the channel's pending code, so it can no longer pair anyone."""
        resource = await self._channel(channel_uid)
        self._pairing.clear(resource.uid)

    async def remove_person(self, channel_uid: str, sender_id: str, *, actor: str) -> None:
        """Un-pair one person: their direct chat and every group they brought the
        bot into, in one write. Everyone else stays paired. Removing the last
        person leaves the channel unpaired — a state it starts in.

        An in-flight turn for a removed person finishes; the next message they
        send is refused like a stranger's."""
        resource = await self._channel(channel_uid)
        person = await self._person(resource, sender_id)
        chats = await self._peers.delete_by_sender(resource.uid, sender_id)
        await self._audit.record(
            AuditEventType.CHANNEL_PERSON_REMOVED.value,
            resource=resource,
            actor=actor,
            details={
                "sender_id": sender_id,
                "display_name": person.display_name,
                "chat_ids": chats,
            },
        )

    def _pair_link(self, channel_uid: str, code: str) -> str:
        """The one-tap pairing link, or "" when this channel cannot make one."""
        username = getattr(self._runtime.adapter(channel_uid), "identity", None)
        return start_link(getattr(username, "username", None) or "", code)

    def _diagnostics(
        self, resource: Resource, *, runs_on: str | None, runs_here: bool
    ) -> tuple[ChannelDiagnostic, ...]:
        """Everything about this channel that reads as configured and is not.

        Two findings, and what they have in common is the failure mode: the
        channel looks right in Coffer and produces silence in the chat, which is
        the one case where saying nothing is worse than any amount of noise.

        An UNBOUND channel runs on no machine at all, because no machine can
        read "nobody in particular" as "me". It is reported here rather than
        left to each surface because it needs nothing but the row itself to
        detect. The neighbouring case — a binding naming a machine that is no
        longer in the registry — deliberately is NOT here: answering it needs
        the registry, which this module cannot reach, and a guess would be
        worse than the surface's own join.

        ``runs_here`` is what keeps that finding honest rather than merely
        literal. A runtime with no machine of its own answers ``True`` to every
        channel, binding gate included, so on such a runtime "unbound" costs
        nothing and reporting it would be describing a rule that is not in
        force.
        """
        findings: list[ChannelDiagnostic] = []
        if resource.enabled and runs_on is None and not runs_here:
            findings.append(
                ChannelDiagnostic(
                    code="channel_not_bound",
                    message=(
                        "This channel is not bound to a machine, so no daemon starts its "
                        "adapter. Bind it to the machine that should answer this bot — a "
                        "channel names one machine precisely so two never answer at once."
                    ),
                )
            )
        return (*findings, *self._privacy_mode_diagnostics(resource))

    def _privacy_mode_diagnostics(self, resource: Resource) -> tuple[ChannelDiagnostic, ...]:
        """spec channels/telegram "Report privacy mode that defeats the group configuration":
        a Telegram bot runs with privacy mode ON by default, which
        withholds ordinary group messages from it entirely. A channel told to
        act on unaddressed group messages under that setting looks correct in
        Coffer and does nothing in the chat."""
        adapter = self._runtime.adapter(resource.uid)
        identity = getattr(adapter, "identity", None)
        if identity is None or getattr(identity, "reads_all_group_messages", None) is not False:
            # No adapter running, not a transport that reports this, or the
            # answer is unknown — an unknown state is never a finding.
            return ()
        if resource.config.get("require_mention", True):
            return ()  # the bot only ever acts when addressed, which it can see
        return (
            ChannelDiagnostic(
                code="telegram_privacy_mode",
                message=(
                    "This channel is set to act on unaddressed group messages, but the bot "
                    "runs with privacy mode ON and cannot see them. Disable privacy mode in "
                    "BotFather (/setprivacy), then remove and re-add the bot to the group."
                ),
            ),
        )

    async def status(self, channel_uid: str) -> ChannelStatus:
        resource = await self._channel(channel_uid)
        name = resource.name
        # Each person's DM thread row (``thread_id=""``) is where the conversation
        # pointer actually lives. It is read beside the pairing rather than stored
        # on it because the two are different lifetimes: the pairing converges
        # between machines, the pointer names a row in THIS machine's store.
        people: list[ChannelPerson] = []
        for person in people_of(await self._peers.list_by_resource(resource.uid)):
            dm = await self._threads.get(resource.uid, person.chat_id, "")
            people.append(
                replace(person, active_conversation_id=dm.active_conversation_id if dm else None)
            )
        channel_type = str(resource.config.get("channel_type", ""))
        inbound: InboundInfo | None = None
        if channel_type == "seatalk":
            inbound = inbound_info(resource, runtime=self._runtime)
        try:
            settings = parse_channel_config(dict(resource.config))
        except ValueError:  # pydantic's ValidationError is one
            settings = None
        raw_binding = resource.config.get("runs_on")
        runs_on = raw_binding if isinstance(raw_binding, str) and raw_binding else None
        # Asked of the runtime rather than resolved here: the runtime is what
        # acts on the answer, so a surface that derived its own could contradict
        # the thing it is reporting on.
        local = await self._runtime.local_machine_id()
        runs_here = local is None or runs_on == local
        return ChannelStatus(
            secret_approval=self._secret_approval(resource),
            diagnostics=self._diagnostics(resource, runs_on=runs_on, runs_here=runs_here),
            uid=resource.uid,
            name=name,
            title=resource.title,
            settings=settings,
            channel_type=channel_type,
            enabled=resource.enabled,
            running=self._runtime.is_running(resource.uid),
            pending_pairing=self._pairing.pending(resource.uid),
            people=tuple(people),
            inbound=inbound,
            runs_on=runs_on,
            # A runtime with no machine of its own is not bound anywhere else
            # either, so it treats every channel as local — the same reading its
            # gate takes.
            runs_here=runs_here,
            starting=resource.enabled and runs_here and self._runtime.start_pending(resource.uid),
        )

    def _secret_approval(self, resource: Resource) -> SecretApproval | None:
        state = self._runtime.secret_withheld(resource.uid)
        if state is None:
            return None
        field = (
            "app_secret_ref"
            if resource.config.get("channel_type") == "seatalk"
            else "bot_token_ref"
        )
        return SecretApproval(state=state, secret_ref=str(resource.config.get(field) or ""))

    async def ingest_event(self, channel_uid: str, envelope: dict[str, object]) -> None:
        """Accept a platform event pushed down the channel's websocket connection.

        Addressed by uid, unlike every other method here, and for a reason none
        of them shares: its caller is not a person. The websocket supervisor
        identifies the channel by the key its connection was started with, which
        is the channel's uid (``runtime_supervision``). A name here would be a
        second spelling that only the plumbing ever writes.

        The call returns when the event has been handled, not when it has been
        scheduled: the websocket connector orders one chat's events by waiting for
        each ``ingest_event`` to finish (spec channels/seatalk "Hand a chat's
        events to the channel in arrival order"), and a forwarded record's file
        download must finish before the text sent behind it is let in. The
        connector runs each call in its own task, so the listen thread never
        waits; handling an event ends at the burst or the command, never at a turn.
        """
        resource = await self._channel(channel_uid)  # unknown uid -> 404
        adapter = self._runtime.adapter(resource.uid)
        if adapter is None or not isinstance(adapter, EventIngestAdapter):
            raise ChannelNotRunning(resource.name)
        await adapter.handle_event(dict(envelope))

    async def notify(
        self, channel_uid: str, text: str, *, actor: str, chat_id: str | None = None
    ) -> None:
        """Push text to one of the channel's paired chats, outside any conversation.

        ``chat_id`` names the chat. Omitted, it is the channel's owner chat —
        its earliest pairing, which is the owner's DM (see
        ``ChannelPeerRepoPort.owner_peer``). That default is load-bearing, not a
        convenience: the caller is "notify this channel", the text is whatever
        the user or a job wrote, and picking an arbitrary paired chat put
        private notifications into group chats. A chat that is not paired to
        this channel is refused rather than messaged.
        """
        resource = await self._channel(channel_uid)
        # The two refusals below name the channel the way its owner does: they
        # are read by a person, and a uid in an error message is a dead end.
        name = resource.name
        if chat_id is None:
            peer = await self._peers.owner_peer(resource.uid)
        else:
            peer = await self._peers.get_by_chat(resource.uid, chat_id)
        if peer is None:
            raise ChannelNotPaired(name)
        adapter = self._runtime.adapter(resource.uid)
        if adapter is None:
            raise ChannelNotRunning(name)
        await adapter.send_text(peer.chat_id, text)

    async def restart(self, channel_uid: str) -> bool:
        """Stop the channel's adapter and bring it up again from its stored
        configuration and secrets (spec channels "Restart a channel's adapter
        on demand"). Returns whether it is running afterwards: a disabled
        channel, or one bound to another machine, is restarted into the state
        it was already in."""
        resource = await self._channel(channel_uid)
        running = await self._runtime.restart(resource.uid)
        _logger.info("channel.restarted", extra={"channel": resource.name, "running": running})
        return running
