"""Channel-kind composition (spec channels) — called from the app lifespan.

Wires the kind, the peer repo, the inbound processor (against the chat
platform's service handles), the adapter factory, the SeaTalk WebSocket
controller, and the reconciling runtime. Runs
AFTER ``wire_chat``, whose result it takes as
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

import hashlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.avatars import PersonAvatars
from coffer.application.channel.inbound import InboundProcessor
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.places import ChannelPlaces
from coffer.application.channel.ports import ChannelAdapter, ChannelBinding
from coffer.application.channel.prompt_note import ChannelNoteReader
from coffer.application.channel.runtime import ChannelRuntime
from coffer.application.channel.service import ChannelService
from coffer.application.channel.thread_tool import ThreadReader, channel_read_thread_tool
from coffer.application.chat import questions
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.chat.question import QuestionBlock
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretDestination, channel_destination
from coffer.infrastructure.channel.avatar_store import FileAvatarStore
from coffer.infrastructure.channel.persistence import (
    ChannelOutboxRepo,
    ChannelPeerRepo,
    ChannelReplyRepo,
    ChannelThreadConversationRepo,
    ChannelThreadCursorRepo,
)
from coffer.infrastructure.channel.seatalk import SeaTalkAdapter
from coffer.infrastructure.channel.seatalk_ws_controller import SeaTalkWebSocketController
from coffer.infrastructure.channel.telegram import TelegramAdapter
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.sync.identity import resolve_identity
from coffer.surfaces.http.channel_credential_wiring import build_credential_check
from coffer.surfaces.http.channel_routes import (
    get_channel_service,
    set_channel_avatars,
    set_channel_service,
    set_credential_check,
)
from coffer.surfaces.http.chat.dependencies import set_channel_note_reader, set_channel_places
from coffer.surfaces.http.chat_wiring import ChatWiring
from coffer.surfaces.http.secret_boundary_wiring import register_resource_destination
from coffer.surfaces.http.secret_composition import boundary_resolver
from coffer.surfaces.http.vault_composition import VaultStores

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.resource_service import ResourceService


class ChatQuestions:
    """The chat platform's questions, as the channel core's port (the channel
    kind never imports the chat kind; this composition root does)."""

    def pending_question_for(self, conversation_id: str) -> QuestionBlock | None:
        return questions.pending_question_for(conversation_id)

    async def answer(
        self,
        conversation_id: str,
        question_id: str,
        *,
        selected: Sequence[str],
        text: str | None,
        via: str,
        by: str,
        index: int | None,
    ) -> QuestionBlock:
        return await questions.answer_question(
            conversation_id,
            question_id,
            [questions.AnswerInput(selected=selected, text=text)],
            via=via,
            by=by,
            index=index,
        )

    async def answer_text(
        self, conversation_id: str, text: str, *, via: str, by: str
    ) -> QuestionBlock | None:
        return await questions.answer_pending_with_text(conversation_id, text, via=via, by=by)


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
    vault: VaultStores,
    secret_store: EncryptedSecretStore,
    chat: ChatWiring,
    builtin_tools: BuiltinToolRegistry,
) -> ChannelRuntime:
    # Derived from the host, cached in ``daemon-config.json``, and stable for
    # the life of the daemon — so it is resolved once here rather than on every
    # reconcile tick and every status read.
    machine_id = resolve_identity().machine_id

    async def local_machine_id() -> str:
        return machine_id

    # Pairings are a vault document per channel that goes with it (spec
    # vault-storage); what each thread is doing is history in runs.db.
    peers = ChannelPeerRepo(name_of=vault.resources.name_of)
    vault.resources.add_follower(peers.documents.follow)
    peers.documents.add_owner_listener(vault.resources.announce)
    threads = ChannelThreadConversationRepo(sm)
    outbox = ChannelOutboxRepo(sm)
    replies = ChannelReplyRepo(sm)
    cursors = ChannelThreadCursorRepo(sm)
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
        # Which platform messages make up each reply, so the owner can withdraw it (spec
        # channels "Withdraw a bot reply on the owner's command").
        replies=replies,
        # How far each conversation has seen each thread (spec channels "Ground a
        # thread turn in a bounded slice of the thread").
        cursors=cursors,
        # Questions an agent asks the owner (spec channels "Ask the owner in the
        # chat and take the chat's answer back to the agent").
        questions=ChatQuestions(),
    )

    # ``materialize_async`` is the resolver's own off-the-loop path;
    # hand-rolling ``to_thread`` here is how the two drifted apart before.
    materialize = boundary_resolver(secret_store).materialize_async
    register_resource_destination("channel", _channel_secret_destination)

    async def adapter_factory(uid: str, config: dict[str, object]) -> ChannelAdapter:
        parsed = parse_channel_config(dict(config))
        # The adapter is named by the channel's uid, which a rename keeps: its
        # inbound messages carry that in ``channel``. The boundary wants the
        # label too, so it is read off the row.
        name = (await resource_svc.get(uid)).name
        if parsed.channel_type == "telegram":
            dest = channel_destination(uid, name, "telegram")
            token = (await materialize({"token": parsed.bot_token_ref}, dest))["token"]
            return TelegramAdapter(uid, token)
        dest = channel_destination(uid, name, "seatalk", parsed.app_id)
        secret = (await materialize({"secret": parsed.app_secret_ref}, dest))["secret"]
        return SeaTalkAdapter(uid, parsed.app_id, secret)

    def secret_revision(ref: str) -> str | None:
        """A stamp of the stored ciphertext, which changes when the secret is
        replaced; it reads the file and never decrypts it, so no key prompt."""
        try:
            data = secret_store.path_of(ref).read_bytes()
        except OSError:
            return None
        return hashlib.sha256(data).hexdigest()[:16]

    # Where each conversation of the Conversations list lives in its channel.
    # Chat reaches it only through its own ``ChannelPlacesPort``, published here.
    set_channel_places(ChannelPlaces(threads=threads))
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
        secret_revision=secret_revision,
        machine_id=local_machine_id,
    )

    # Each paired person's picture, asked of the running adapter when the
    # Channels page wants it (spec channels "Show each paired person's platform
    # picture").
    avatars = PersonAvatars(store=FileAvatarStore(), peers=peers, adapter_of=runtime.adapter)
    set_channel_avatars(avatars)

    async def on_delete(channel: Resource) -> None:
        await runtime.evict(channel)
        avatars.forget(channel.uid)
        # The history rows name the channel by uid and nothing cascades from
        # a file, so they go here, with the channel.
        await threads.delete_for_channel(channel.uid)
        await outbox.delete_for_channel(channel.uid)
        await replies.delete_for_channel(channel.uid)
        await cursors.delete_for_channel(channel.uid)

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

    async def running_channel(ref: str) -> ChannelBinding | None:
        """The running binding of the channel named (or uid'd) ``ref``."""
        for channel in await resource_svc.list(kind="channel"):
            if ref in (channel.uid, channel.name):
                return processor.binding(channel.uid)
        return None

    # An agent reads a thread's older messages on demand (spec channels "Read a
    # thread's earlier messages on demand").
    builtin_tools.register(
        channel_read_thread_tool(ThreadReader(resolve=running_channel, peers=peers))
    )
    set_credential_check(build_credential_check(resource_svc, materialize))
    return runtime


def _channel_secret_destination(
    resource: Resource,
) -> tuple[SecretDestination, dict[str, str]] | None:
    """Where a channel's secret goes, for the secret boundary's listing."""
    parsed = parse_channel_config(dict(resource.config))
    if parsed.channel_type == "telegram":
        dest = channel_destination(resource.uid, resource.name, "telegram")
        return dest, {"token": parsed.bot_token_ref}
    dest = channel_destination(resource.uid, resource.name, "seatalk", parsed.app_id)
    return dest, {"secret": parsed.app_secret_ref}
