"""Channel-kind composition (spec channels) — called from the app lifespan.

Wires the kind, the peer repo, the inbound processor (against the chat
platform's service handles), the adapter factory, the callback-listener
controller, the SeaTalk WebSocket controller, and the reconciling runtime. Runs
AFTER ``wire_chat`` and ``wire_knowledge_kind``, whose results it takes as
parameters.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.channel.inbound import InboundProcessor
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.runtime import ChannelRuntime
from coffer.application.channel.service import ChannelService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.channel.listener_spawn import CallbackListenerController
from coffer.infrastructure.channel.persistence import (
    ChannelPeerRepo,
    ChannelThreadConversationRepo,
)
from coffer.infrastructure.channel.seatalk import SeaTalkAdapter
from coffer.infrastructure.channel.seatalk_ws_controller import SeaTalkWebSocketController
from coffer.infrastructure.channel.telegram import TelegramAdapter
from coffer.infrastructure.channel.tunnel_spawn import TunnelController
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.auth import get_active_token
from coffer.surfaces.http.channel_routes import get_channel_service, set_channel_service
from coffer.surfaces.http.chat_wiring import ChatWiring
from coffer.surfaces.http.knowledge_wiring import KnowledgeWiring

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.resource_service import ResourceService


def _daemon_info() -> tuple[str, str]:
    """Resolved at call time BY DESIGN: the token and port are published by the
    lifespan after this kind is wired (daemon.json is read later), and the
    listener only asks on its first tick."""
    token = get_active_token()
    if token is None:
        raise RuntimeError("daemon token not published yet")
    return f"http://127.0.0.1:{daemon_routes.get_port()}", token


async def _ingest_websocket_event(name: str, envelope: dict[str, Any]) -> None:
    """Hand a websocket-delivered event to the same ingest the webhook route uses.

    Resolved at call time BY DESIGN: ``ChannelService`` is built at the end of
    ``wire_channel_kind``, after the runtime this feeds, and the self-reference
    cannot be handed in before it exists."""
    await get_channel_service().ingest_event(name, envelope)


def wire_channel_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    credential_store: EncryptedCredentialStore,
    chat: ChatWiring,
    knowledge: KnowledgeWiring,
) -> ChannelRuntime:
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
        # `/save` (spec knowledge FR-036): both already satisfy the channel
        # core's Protocol shape structurally (``CollectionCatalogPort`` /
        # ``IngestPort``), so the knowledge kind's own services go in
        # directly — the channel core never imports the knowledge kind itself
        # (import-linter contract 5f).
        collections=knowledge.service,
        ingest=knowledge.ingest_service,
    )

    resolver = CredentialResolver(credential_store)

    async def materialize(refs: dict[str, str]) -> dict[str, str]:
        # The store read is blocking (CODE-034) — never call it on the event loop.
        return await asyncio.to_thread(resolver.materialize, refs)

    async def adapter_factory(name: str, config: dict[str, object]) -> ChannelAdapter:
        parsed = parse_channel_config(dict(config))
        if parsed.channel_type == "telegram":
            token = (await materialize({"token": parsed.bot_token_ref}))["token"]
            return TelegramAdapter(name, token)
        secret = (await materialize({"secret": parsed.app_secret_ref}))["secret"]
        return SeaTalkAdapter(name, parsed.app_id, secret)

    listener = CallbackListenerController(daemon_info=_daemon_info)
    runtime = ChannelRuntime(
        resources=resource_svc,
        adapter_factory=adapter_factory,
        processor=processor,
        pairing=pairing,
        listener=listener,
        tunnel=TunnelController(),
        # FR-071: websocket-delivery channels converge the same way, and their
        # inbound events land on the same seam the webhook route uses —
        # ``ChannelService.ingest_event``, which does not exist yet at this point
        # in the wiring, so it is resolved at call time exactly as the daemon's
        # URL and token are in ``_daemon_info``.
        websockets=SeaTalkWebSocketController(ingest=_ingest_websocket_event),
        materialize=materialize,
    )

    async def on_delete(ref: ResourceRef) -> None:
        await runtime.evict(ref.name)

    async def channel_scope(ref: ResourceRef) -> Scope | None:
        """The channel's own scope, for the edit-time default_agent check. Read
        live off the row rather than cached: an edit lands after whatever scope
        the row carries right now."""
        return (await resource_svc.get(ref)).scope

    app.state.kinds["channel"] = make_channel_kind(
        on_delete=on_delete,
        # Validate a channel's default_agent against the live agent registry at
        # create/edit, so an unknown agent (e.g. the retired "builtin") is
        # rejected up front instead of failing silently on the first turn.
        agent_keys=chat.registry.agent_keys,
        # ...and against the agents this channel may drive (ADR per-agent-resource-scope), so
        # an edit cannot bind it to an agent its scope excludes.
        scope_of=channel_scope,
    )

    service = ChannelService(
        resources=resource_svc,
        peers=peers,
        pairing=pairing,
        runtime=runtime,
        audit=audit,
        # The callback self-test resolves the signing secret and probes the
        # public URL over the network.
        materialize=materialize,
        http_client=httpx.AsyncClient(),
    )
    set_channel_service(service)
    # Pairing identity registers no synced state area. It used to: the argument
    # was that pairings are platform-level, so rebinding a channel to another
    # machine would need no re-pairing. A channel does not reach another machine
    # any more (spec vault-sync ``## What does not sync``), so there is no
    # rebinding for the pairings to save — every pulled document would name a
    # channel the other machine does not have and be skipped forever, and the
    # only thing publishing them still achieved was putting chat ids, display
    # names and sender ids in the remote for nothing.
    return runtime
