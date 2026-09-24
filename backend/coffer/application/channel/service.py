"""ChannelService — pairing codes, status, notify, event ingest.

The REST routes and CLI talk to this; adapter lifecycle belongs to
ChannelRuntime and message flow to InboundProcessor.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.channel.inbound_status import InboundInfo, inbound_info
from coffer.application.channel.pairing import PairingManager, start_link
from coffer.application.channel.ports import EventIngestAdapter
from coffer.application.channel.store_ports import (
    ChannelPeer,
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.channel.errors import ChannelNotPaired, ChannelNotRunning
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
    peer: ChannelPeer | None
    # The conversation the owner's DM is currently driving, read from the
    # thread-conversation table (``thread_id=""`` is the DM). It is reported
    # beside ``peer`` rather than on it because a pairing and a conversation
    # pointer are different lifetimes: the pairing converges between machines,
    # the pointer names a row in THIS machine's conversation store.
    peer_conversation_id: str | None
    # A SeaTalk channel's websocket connection; None for telegram, whose
    # inbound is the adapter's own polling and is reported by ``running``.
    inbound: InboundInfo | None
    # spec channels "Diagnose configuration a platform setting defeats": contradictions
    # between the configuration and what the platform actually permits. Empty is the
    # healthy case.
    diagnostics: tuple[ChannelDiagnostic, ...] = ()
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
        self._ingest_tasks: set[asyncio.Task[None]] = set()

    async def _channel(self, channel_uid: str) -> Resource:
        """The channel row, by its identity.

        Every method here addresses a channel by ``uid`` (ADR
        resource-identity-is-an-immutable-uid). A name reaches Coffer only where
        a person typed one — the CLI resolves it and the web UI never had it —
        and a service that accepted both would be the round trip this change
        exists to delete: the route resolving uid → name so that the service can
        resolve name → row. Whatever needs the label past this line reads it off
        the row.
        """
        return await self._resources.get(channel_uid)

    async def issue_pairing_code(
        self, channel_uid: str, *, actor: str
    ) -> tuple[str, datetime, str]:
        """Generate a pairing code for the channel (replacing any pending one).

        Returns the code, its expiry, and — where the platform has a
        parameterised start link and the bot's username is known — a link that
        carries the code (see "Pair by a one-tap start link"), so the owner
        pairs by opening it instead of transcribing eight characters on a phone.
        The link is "" when there is none; the typed code always works.
        """
        resource = await self._channel(channel_uid)
        # The pending-code map and the running-adapter map are both keyed by the
        # channel's NAME: they are in-memory state the runtime rebuilds from the
        # resource table on every tick, so a rename simply re-keys them.
        name = resource.name
        code, expires_at = self._pairing.issue(name)
        await self._audit.record(
            AuditEventType.CHANNEL_PAIRING_ISSUED.value,
            resource=resource,
            actor=actor,
            details={"expires_at": expires_at.isoformat()},
        )
        return code, expires_at, self._pair_link(name, code)

    def _pair_link(self, name: str, code: str) -> str:
        """The one-tap pairing link, or "" when this channel cannot make one."""
        username = getattr(self._runtime.adapter(name), "identity", None)
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
        adapter = self._runtime.adapter(resource.name)
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
        peer = await self._peers.owner_peer(resource.id)
        # The DM's own thread row (``thread_id=""``) is where the conversation
        # pointer actually lives. ``channel_peers`` carried a column of the
        # same name that nothing ever wrote, so this line used to report None
        # for every channel that had been talking for weeks.
        dm = await self._threads.get(resource.id, peer.chat_id, "") if peer else None
        channel_type = str(resource.config.get("channel_type", ""))
        inbound: InboundInfo | None = None
        if channel_type == "seatalk":
            inbound = inbound_info(resource, runtime=self._runtime)
        raw_binding = resource.config.get("runs_on")
        runs_on = raw_binding if isinstance(raw_binding, str) and raw_binding else None
        # Asked of the runtime rather than resolved here: the runtime is what
        # acts on the answer, so a surface that derived its own could contradict
        # the thing it is reporting on.
        local = await self._runtime.local_machine_id()
        runs_here = local is None or runs_on == local
        return ChannelStatus(
            diagnostics=self._diagnostics(resource, runs_on=runs_on, runs_here=runs_here),
            uid=resource.uid,
            name=name,
            channel_type=channel_type,
            enabled=resource.enabled,
            running=self._runtime.is_running(name),
            pending_pairing=self._pairing.pending(name),
            peer=peer,
            peer_conversation_id=dm.active_conversation_id if dm else None,
            inbound=inbound,
            runs_on=runs_on,
            # A runtime with no machine of its own is not bound anywhere else
            # either, so it treats every channel as local — the same reading its
            # gate takes.
            runs_here=runs_here,
        )

    async def ingest_event(self, channel_uid: str, envelope: dict[str, object]) -> None:
        """Accept a platform event pushed down the channel's websocket connection.

        Addressed by uid, unlike every other method here, and for a reason none
        of them shares: its caller is not a person. The websocket supervisor
        identifies the channel by the key its connection was started with, which
        is the channel's uid (``runtime_supervision``). A name here would be a
        second spelling that only the plumbing ever writes.

        Processing is scheduled in the background: the connection's listen
        thread must not wait on a turn, and a command/pairing reply can involve
        rate-limited outbound API calls.
        """
        resource = await self._channel(channel_uid)  # unknown uid -> 404
        name = resource.name
        adapter = self._runtime.adapter(name)
        if adapter is None or not isinstance(adapter, EventIngestAdapter):
            raise ChannelNotRunning(name)
        task = asyncio.create_task(adapter.handle_event(dict(envelope)))
        self._ingest_tasks.add(task)
        task.add_done_callback(self._reap_ingest_task)

    def _reap_ingest_task(self, task: asyncio.Task[None]) -> None:
        self._ingest_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _logger.error("channel.ingest.failed", exc_info=task.exception())

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
            peer = await self._peers.owner_peer(resource.id)
        else:
            peer = await self._peers.get_by_chat(resource.id, chat_id)
        if peer is None:
            raise ChannelNotPaired(name)
        adapter = self._runtime.adapter(name)
        if adapter is None:
            raise ChannelNotRunning(name)
        await adapter.send_text(peer.chat_id, text)
