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
from coffer.domain.provider.config import ProviderConfig
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
    get_model_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.dependencies import get_provider_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from coffer.application.resource_service import ResourceService


def _daemon_info() -> tuple[str, str]:
    token = get_active_token()
    if token is None:
        raise RuntimeError("daemon token not published yet")
    return f"http://127.0.0.1:{daemon_routes.get_port()}", token


class _ModelCatalog:
    """Adapts the model registry to the channel core's ModelCatalogPort: resolve
    a chat-typed name (display name, id, or upstream model string) to a model id."""

    def __init__(self, models: Any) -> None:
        self._models = models

    async def resolve(self, name: str) -> str | None:
        lowered = name.lower()
        for m in await self._models.list():
            if m.id == name or m.display_name.lower() == lowered or m.model == name:
                return str(m.id)
        return None

    async def list_models(self) -> list[tuple[str, str]]:
        return [(str(m.id), str(m.display_name)) for m in await self._models.list()]


# A managed chat agent's agent_key -> its provider wire format (ADR-032 targets).
_WIRE_BY_AGENT = {"claude_code": "anthropic", "codex": "openai"}


class _ModelSuggestions:
    """ModelSuggestionPort: best-effort model quick-picks for a managed agent's
    ``/model`` card — the active provider profile's ``model`` (+ ``fast_model``)
    for the agent's wire (ADR-032), mirroring the web model picker. Empty on any
    miss (no provider service, no active profile, unknown agent), so the card
    falls back to the free-text path."""

    def __init__(self, provider_service_getter: Any) -> None:
        self._get = provider_service_getter

    async def suggest(self, agent_key: str) -> list[str]:
        wire = _WIRE_BY_AGENT.get(agent_key)
        if wire is None:
            return []
        try:
            resources = await self._get().list()
        except Exception:
            return []
        picks: list[str] = []
        for r in resources:
            cfg = ProviderConfig.model_validate(r.config)
            if cfg.wire_format.value != wire or not cfg.is_active:
                continue
            for m in (cfg.model, cfg.fast_model):
                if m and m not in picks:
                    picks.append(m)
            break
        return picks


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
        models=_ModelCatalog(get_model_service()),
        model_suggestions=_ModelSuggestions(get_provider_service),
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
