"""Channel-kind composition (spec 009) — called from the app lifespan.

Wires the kind, the peer repo, the inbound processor (against the chat
platform's service handles), the adapter factory, the callback-listener
controller, and the reconciling runtime. Must run AFTER ``wire_chat``.
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
from coffer.infrastructure.channel.listener_spawn import CallbackListenerController
from coffer.infrastructure.channel.persistence import ChannelPeerRepo
from coffer.infrastructure.channel.seatalk import SeaTalkAdapter
from coffer.infrastructure.channel.telegram import TelegramAdapter
from coffer.infrastructure.channel.tunnel_spawn import TunnelController
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.auth import get_active_token
from coffer.surfaces.http.channel_routes import set_channel_service
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_turn_orchestrator,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from coffer.application.resource_service import ResourceService


def _daemon_info() -> tuple[str, str]:
    token = get_active_token()
    if token is None:
        raise RuntimeError("daemon token not published yet")
    return f"http://127.0.0.1:{daemon_routes.get_port()}", token


# Curated built-in model quick-picks per managed agent type — the models
# reachable through the agent's OWN login (mirrors the web ModelPicker's
# no-connection case + frontend BUILTIN_MODELS_BY_AGENT). The connection no
# longer carries a model (spec 011 E3), so the channel /model card offers these.
_BUILTIN_MODELS_BY_AGENT = {
    "claude_code": ["opus", "sonnet", "haiku"],
    "codex": ["gpt-5-codex", "gpt-5", "o3"],
}


class _ModelSuggestions:
    """ModelSuggestionPort: best-effort model quick-picks for a managed agent's
    ``/model`` card — the agent's curated built-in models. Empty for an unknown
    agent, so the card falls back to the free-text path."""

    async def suggest(self, agent_key: str) -> list[str]:
        return list(_BUILTIN_MODELS_BY_AGENT.get(agent_key, []))


def wire_channel_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    credential_store: Any = None,
) -> ChannelRuntime:
    peers = ChannelPeerRepo(sm)
    pairing = PairingManager()
    processor = InboundProcessor(
        peers=peers,
        pairing=pairing,
        conversations=get_chat_service(),
        turns=get_turn_orchestrator(),
        audit=audit,
        agents=get_agent_registry(),
        model_suggestions=_ModelSuggestions(),
    )

    # Production injects the EncryptedCredentialStore; None (tests) falls back
    # to the OS keychain adapter, which resolves nothing unless seeded.
    store = credential_store if credential_store is not None else KeyringAdapter()
    resolver = CredentialResolver(store)

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
        materialize=materialize,
    )

    async def on_delete(ref: ResourceRef) -> None:
        await runtime.evict(ref.name)

    app.state.kinds["channel"] = make_channel_kind(
        on_delete=on_delete,
        # Validate a channel's default_agent against the live agent registry at
        # create/edit, so an unknown agent (e.g. the retired "builtin") is
        # rejected up front instead of failing silently on the first turn.
        agent_keys=lambda: get_agent_registry().agent_keys(),
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
    return runtime
