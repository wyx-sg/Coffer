"""Channel-kind composition (spec channels) — called from the app lifespan.

Wires the kind, the peer repo, the inbound processor (against the chat
platform's service handles), the adapter factory, the SeaTalk WebSocket
controller, and the reconciling runtime. Runs
AFTER ``wire_chat`` and ``wire_knowledge_kind``, whose results it takes as
parameters.

It also resolves this machine's identity, because a channel names the one
machine whose daemon runs its adapter (spec channels "Bind each channel to the
one machine that runs it") and both the runtime's gate and the kind's
validators need the same answer. It is read here rather than taken from the
sync module because sync is wired LATER — and because the binding is not a sync
feature: it decides which daemon starts an adapter whether or not this vault
converges with anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.channel.inbound import InboundProcessor
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.mirror import ChannelMirror
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.prompt_note import ChannelNoteReader
from coffer.application.channel.runtime import ChannelRuntime
from coffer.application.channel.service import ChannelService
from coffer.application.channel.sync_state import ChannelPeerSyncState
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretDestination, channel_destination
from coffer.infrastructure.channel.persistence import (
    ChannelOutboxRepo,
    ChannelPeerRepo,
    ChannelThreadConversationRepo,
)
from coffer.infrastructure.channel.seatalk import SeaTalkAdapter
from coffer.infrastructure.channel.seatalk_ws_controller import SeaTalkWebSocketController
from coffer.infrastructure.channel.telegram import TelegramAdapter
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.sync.identity import resolve_identity
from coffer.surfaces.http.channel_routes import get_channel_service, set_channel_service
from coffer.surfaces.http.chat.dependencies import set_channel_mirror, set_channel_note_reader
from coffer.surfaces.http.chat_wiring import ChatWiring
from coffer.surfaces.http.credential_composition import boundary_resolver
from coffer.surfaces.http.knowledge_wiring import KnowledgeWiring
from coffer.surfaces.http.secret_boundary_wiring import register_resource_destination
from coffer.surfaces.http.sync_contributions import SyncContributions

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.resource_service import ResourceService


async def _ingest_websocket_event(channel_uid: str, envelope: dict[str, Any]) -> None:
    """Hand a websocket-delivered event to the channel's one ingest entry point.

    The controller supervises its sockets by channel uid, so what arrives here
    is an identity, not a label, and it goes straight through.

    Resolved at call time BY DESIGN: ``ChannelService`` is built at the end of
    ``wire_channel_kind``, after the runtime this feeds, and the self-reference
    cannot be handed in before it exists."""
    await get_channel_service().ingest_event(channel_uid, envelope)


def wire_channel_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    credential_store: EncryptedCredentialStore,
    chat: ChatWiring,
    knowledge: KnowledgeWiring,
    sync: SyncContributions,
) -> ChannelRuntime:
    # Derived from the host, cached in ``daemon-config.json``, and stable for
    # the life of the daemon — so it is resolved once here rather than on every
    # reconcile tick and every status read.
    machine_id = resolve_identity().machine_id
    features = app.state.feature_service

    async def local_machine_id() -> str:
        return machine_id

    peers = ChannelPeerRepo(sm)
    threads = ChannelThreadConversationRepo(sm)
    pairing = PairingManager()
    processor = InboundProcessor(
        peers=peers,
        threads=threads,
        pairing=pairing,
        conversations=chat.chat_service,
        turns=chat.orchestrator,
        audit=audit,
        agents=chat.registry,
        # The /model card offers the same catalogue as everything else; the
        # catalogue service's ``suggest`` IS the ModelSuggestionPort shape, so
        # it goes in directly rather than through a hardcoded local list.
        model_suggestions=chat.model_catalogue,
        # `/kb` (spec channels "Save a sent document into a collection"): both
        # already satisfy the channel
        # core's Protocol shape structurally (``CollectionCatalogPort`` /
        # ``IngestPort``), so the knowledge kind's own services go in
        # directly — the channel core never imports the knowledge kind itself
        # (import-linter contract 5f).
        collections=knowledge.service,
        ingest=knowledge.ingest_service,
        # While knowledge is switched off `/kb` answers that and saves
        # nothing (spec experimental-features).
        knowledge_enabled=lambda: features.is_enabled("knowledge"),
    )

    # ``materialize_async`` is the resolver's own off-the-loop path;
    # hand-rolling ``to_thread`` here is how the two drifted apart before.
    materialize = boundary_resolver(credential_store).materialize_async
    register_resource_destination("channel", _channel_secret_destination)

    async def adapter_factory(name: str, config: dict[str, object]) -> ChannelAdapter:
        parsed = parse_channel_config(dict(config))
        # The boundary is keyed by the channel's uid, which a rename keeps.
        row = await resource_svc.find_by_name("channel", name)
        uid = row.uid if row is not None else f"name:{name}"
        if parsed.channel_type == "telegram":
            dest = channel_destination(uid, name, "telegram")
            token = (await materialize({"token": parsed.bot_token_ref}, dest))["token"]
            return TelegramAdapter(name, token, knowledge_enabled=features.is_enabled("knowledge"))
        dest = channel_destination(uid, name, "seatalk", parsed.app_id)
        secret = (await materialize({"secret": parsed.app_secret_ref}, dest))["secret"]
        return SeaTalkAdapter(name, parsed.app_id, secret)

    # A reply typed on the Chat page into a channel's conversation also goes to
    # that chat (spec chat "Mirror a web reply into the channel it came from").
    # Chat reaches it only through its own ``ChannelMirrorPort``, published here.
    mirror = ChannelMirror(
        resources=resource_svc,
        threads=threads,
        peers=peers,
        outbox=ChannelOutboxRepo(sm),
        processor=processor,
    )
    set_channel_mirror(mirror)
    # The facts the channel note of a channel-driven turn is written from (spec
    # channels "Tell a channel-driven agent it is on a chat channel"): chat
    # composes the note, only the channel kind knows platform, chat kind and
    # what the running transport renders.
    set_channel_note_reader(
        ChannelNoteReader(resources=resource_svc, threads=threads, binding=processor.binding)
    )

    runtime = ChannelRuntime(
        resources=resource_svc,
        adapter_factory=adapter_factory,
        processor=processor,
        pairing=pairing,
        # spec channels/seatalk "Receive every event over one outbound websocket
        # connection": every SeaTalk event lands on the channel's one ingest
        # seam — ``ChannelService.ingest_event``, which does not exist yet at
        # this point in the wiring, so it is resolved at call time.
        websockets=SeaTalkWebSocketController(ingest=_ingest_websocket_event),
        materialize=materialize,
        machine_id=local_machine_id,
        knowledge_enabled=lambda: features.is_enabled("knowledge"),
        # Each tick delivers what a running channel still owes its chats.
        on_tick=mirror.flush,
    )

    async def on_delete(channel: Resource) -> None:
        await runtime.evict(channel)

    async def agent_names() -> dict[str, str]:
        """Every registered agent's UID mapped to its name.

        One direction, one vocabulary. This used to be a name→key map feeding
        three separate injections, because an agent answered to two names and a
        channel's scope and its ``default_agent`` were written in different
        ones. Both hold uids now, so the comparisons need no translation at all
        and the only thing left to resolve is the label a human reads.
        """
        return {r.uid: r.name for r in await resource_svc.list(kind="agent")}

    app.state.kinds["channel"] = make_channel_kind(
        on_delete=on_delete,
        # Validate a channel's default_agent against the live agent registry on
        # BOTH write paths, so a channel cannot be created — or edited — bound
        # to an agent that does not exist and fail silently on the first turn.
        agent_names=agent_names,
        # ...except for a channel bound to another machine, whose agents are
        # that machine's business. Without this a converged channel would be
        # refused at this registry's door for a fault on nobody's machine.
        local_machine_id=machine_id,
    )

    service = ChannelService(
        resources=resource_svc,
        peers=peers,
        threads=threads,
        pairing=pairing,
        runtime=runtime,
        audit=audit,
    )
    set_channel_service(service)
    # Pairing identity is a synced state area again. It was removed when
    # channels stopped travelling — a published pairing would have named a
    # channel the other machine did not have — and that premise is gone: a
    # channel travels, so rebinding it to another machine is a thing that
    # happens, and pairings are what make a rebind cost nothing. They carry
    # platform identity only; the conversation pointer stays on this machine.
    #
    # Appended to the ``SyncContributions`` collector every other area uses
    # (``app_mcp_composition``, ``engine_config_composition``,
    # ``agent_skill_wiring``); ``start_sync`` reads it once every kind is wired.
    # It must go through that object and not onto ``app.state``: nothing reads
    # ``app.state`` for state providers, so an area that registers there
    # silently does not converge.
    sync.state_providers.append(ChannelPeerSyncState(resource_svc, peers))
    return runtime


def _channel_secret_destination(
    resource: Resource,
) -> tuple[SecretDestination, dict[str, str]] | None:
    """Where a channel's credential goes, for the secret boundary's listing."""
    parsed = parse_channel_config(dict(resource.config))
    if parsed.channel_type == "telegram":
        dest = channel_destination(resource.uid, resource.name, "telegram")
        return dest, {"token": parsed.bot_token_ref}
    dest = channel_destination(resource.uid, resource.name, "seatalk", parsed.app_id)
    return dest, {"secret": parsed.app_secret_ref}
