"""A reply typed on the Chat page into a channel's conversation also reaches that
chat (spec chat "Mirror a web reply into the channel it came from").

Driven through the real chat routes (conversation + turn) on the channel
fixture's real chat platform and channel core, with ``ChannelMirror`` wired as
the composition root wires it; only the transport is the recording fake.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from coffer.application.channel.inbound import ChannelBinding
from coffer.application.channel.mirror import ChannelMirror
from coffer.application.channel.runtime import ChannelRuntime
from coffer.application.chat.attachments import ChatAttachmentService
from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.domain.resource import Resource
from coffer.infrastructure.channel.persistence import ChannelOutboxRepo
from coffer.infrastructure.chat.media_store import FileChatMediaStore
from coffer.infrastructure.persistence.engine import session_maker
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_attachment_service,
    get_channel_mirror,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import get_resource_service

from .conftest import ChannelEnv, FakeChannelAdapter, default_reply_adapter, inbound, wait_until

_TOKEN = "mirror-token"


class _RefusingAdapter(FakeChannelAdapter):
    """A transport whose sends the platform refuses."""

    async def send_text(
        self,
        chat_id: str,
        markdown: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        title: str = "",
        thread_id: str = "",
        chat_kind: str = "direct",
        reply_to_message_id: str = "",
        ephemeral: Any = None,
    ) -> SentMessage:
        raise RuntimeError("platform refused the message")


class _Web:
    def __init__(self, env: ChannelEnv, tmp_path: Path) -> None:
        self.env = env
        self.outbox = ChannelOutboxRepo(session_maker(env.engine))
        self.mirror = ChannelMirror(
            resources=env.resources,
            threads=env.threads,
            peers=env.peers,
            outbox=self.outbox,
            processor=env.processor,
        )
        app = FastAPI()
        err_handlers.register(app)
        app.include_router(conversation_router)
        app.include_router(turn_router)
        attachments = ChatAttachmentService(FileChatMediaStore(tmp_path / "chat-media"))
        app.dependency_overrides[get_chat_service] = lambda: env.chat
        app.dependency_overrides[get_turn_orchestrator] = lambda: env.orchestrator
        app.dependency_overrides[get_attachment_service] = lambda: attachments
        app.dependency_overrides[get_resource_service] = lambda: env.resources
        app.dependency_overrides[get_channel_mirror] = lambda: self.mirror
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Coffer-Token": _TOKEN},
        )

    async def reply(self, conversation_id: str, text: str) -> dict[str, Any]:
        resp = await self.client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages", json={"text": text}
        )
        assert resp.status_code == 202, resp.text
        return dict(resp.json())

    async def mirror_view(self, conversation_id: str) -> dict[str, Any]:
        resp = await self.client.get(f"/api/v1/chat/conversations/{conversation_id}")
        assert resp.status_code == 200, resp.text
        return dict(resp.json()["channel_binding"]["mirror"])


@pytest_asyncio.fixture
async def web(env: ChannelEnv, tmp_path: Path) -> AsyncIterator[_Web]:
    set_active_token(_TOKEN)
    w = _Web(env, tmp_path)
    try:
        yield w
    finally:
        await w.client.aclose()
        set_active_token(None)


async def _channel(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel()
    # No live surface: the answer arrives as one plain send, easy to assert on.
    adapter = env.bind(resource, FakeChannelAdapter(supports_edit=False))
    await env.pair(resource, "owner", sender_id="owner-1")
    return resource, adapter


async def _conversation_from_chat(
    env: ChannelEnv,
    resource: Resource,
    adapter: FakeChannelAdapter,
    *,
    chat_id: str = "owner",
    thread_id: str = "",
    chat_kind: str = "direct",
) -> str:
    """Let the chat open a conversation with one message and its answer."""
    before = len(adapter.sent)
    await env.send(
        inbound(
            "tg",
            chat_id,
            "hello from the chat",
            thread_id=thread_id,
            chat_kind=chat_kind,
            sender_id="owner-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts()[before:])
    conversation_id = await env.active_conversation(resource, chat_id, thread_id)
    assert conversation_id is not None
    await wait_until(lambda: env.orchestrator.pending(conversation_id) == [])
    return conversation_id


@pytest.mark.acceptance(
    spec="chat", scenario="a web reply reaches the channel chat marked as from Coffer"
)
async def test_a_web_reply_reaches_the_chat_marked_as_from_coffer(
    env: ChannelEnv, web: _Web
) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(env, resource, adapter)

    ack = await web.reply(conversation_id, "check the deploy")

    assert ack["mirror"] == "sent"
    assert ("owner", "(from Coffer) check the deploy", "", "direct") in adapter.sent_routed


@pytest.mark.acceptance(
    spec="chat", scenario="the agent's answer to a web reply is delivered to the channel"
)
async def test_the_answer_to_a_web_reply_is_delivered_to_the_chat(
    env: ChannelEnv, web: _Web
) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(env, resource, adapter)
    env.provider.adapter = default_reply_adapter("the deploy is green")

    await web.reply(conversation_id, "check the deploy")

    await wait_until(lambda: "the deploy is green" in adapter.texts())
    texts = adapter.texts()
    assert texts.index("(from Coffer) check the deploy") < texts.index("the deploy is green")
    routed = [r for r in adapter.sent_routed if r[1] == "the deploy is green"]
    assert routed == [("owner", "the deploy is green", "", "direct")]


@pytest.mark.acceptance(
    spec="chat", scenario="a web reply to a group main-chat conversation stays in Coffer"
)
async def test_a_web_reply_to_a_group_main_chat_stays_in_coffer(env: ChannelEnv, web: _Web) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(
        env, resource, adapter, chat_id="grp-1", chat_kind="group"
    )
    env.provider.adapter = default_reply_adapter("only on the web")

    ack = await web.reply(conversation_id, "just for me")

    assert ack["mirror"] == "kept"
    await wait_until(lambda: env.orchestrator.pending(conversation_id) == [])
    view = await web.mirror_view(conversation_id)
    assert view["deliverable"] is False
    assert view["reason"] == "group_main"
    assert not any("just for me" in t for t in adapter.texts())
    assert await web.outbox.pending_for_conversation(conversation_id) == []


@pytest.mark.acceptance(spec="chat", scenario="a reply the channel cannot send is kept and retried")
async def test_a_reply_the_channel_cannot_send_is_kept_and_retried(
    env: ChannelEnv, web: _Web
) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(env, resource, adapter)
    env.processor.unbind(resource.uid)  # the channel is not running
    env.provider.adapter = default_reply_adapter("answered while away")

    ack = await web.reply(conversation_id, "are you there")

    assert ack["mirror"] == "pending"
    await wait_until(
        lambda: _count(web.outbox.pending_for_conversation(conversation_id), 2),
        message="the answer was not kept behind the reply",
    )
    view = await web.mirror_view(conversation_id)
    assert [(u["kind"], u["text"]) for u in view["undelivered"]] == [
        ("reply", "(from Coffer) are you there"),
        ("answer", "answered while away"),
    ]

    # The platform refuses at first: nothing is lost, nothing is marked.
    refusing = env.bind(resource, _RefusingAdapter())
    await web.mirror.flush(_binding(env, resource))
    assert len(await web.outbox.pending_for_conversation(conversation_id)) == 2
    assert refusing.sent == []

    # Running again: delivered in order and marked delivered.
    back = env.bind(resource, FakeChannelAdapter(supports_edit=False))
    web.mirror._failed_at.clear()  # past the backoff
    await web.mirror.flush(_binding(env, resource))
    assert back.sent_routed == [
        ("owner", "(from Coffer) are you there", "", "direct"),
        ("owner", "answered while away", "", "direct"),
    ]
    assert await web.outbox.pending_for_conversation(conversation_id) == []
    assert (await web.mirror_view(conversation_id))["undelivered"] == []


async def test_a_refused_send_keeps_the_reply_pending(env: ChannelEnv, web: _Web) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(env, resource, adapter)
    env.bind(resource, _RefusingAdapter())

    ack = await web.reply(conversation_id, "try this")

    assert ack["mirror"] == "pending"
    owed = await web.outbox.pending_for_conversation(conversation_id)
    assert owed[0].kind == "reply" and owed[0].text == "(from Coffer) try this"


async def test_a_flush_after_a_failure_waits_out_the_backoff(env: ChannelEnv, web: _Web) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(env, resource, adapter)
    env.processor.unbind(resource.uid)
    await web.reply(conversation_id, "later")
    env.bind(resource, _RefusingAdapter())
    await web.mirror.flush(_binding(env, resource))

    back = env.bind(resource, FakeChannelAdapter(supports_edit=False))
    await web.mirror.flush(_binding(env, resource))

    assert back.sent == []  # inside the 30 s backoff


async def test_the_runtime_tick_flushes_each_running_channel(env: ChannelEnv) -> None:
    resource = await env.register_channel()
    seen: list[str] = []

    async def hook(binding: ChannelBinding) -> None:
        seen.append(binding.resource.name)
        raise RuntimeError("a hook failure never breaks the tick")

    runtime = ChannelRuntime(
        resources=env.resources,
        adapter_factory=env.adapter_factory,
        processor=env.processor,
        pairing=env.pairing,
        interval_seconds=0.05,
        on_tick=hook,
    )
    await runtime.reconcile_once()
    await runtime.reconcile_once()

    assert seen == [resource.name, resource.name]
    assert runtime.is_running(resource.uid)
    await runtime.dispose()


@pytest.mark.acceptance(spec="chat", scenario="the conversation says where a reply will also go")
async def test_the_conversation_says_where_a_reply_will_also_go(env: ChannelEnv, web: _Web) -> None:
    resource, adapter = await _channel(env)
    direct = await _conversation_from_chat(env, resource, adapter)
    topic = await _conversation_from_chat(
        env, resource, adapter, chat_id="grp-1", thread_id="th-1", chat_kind="group"
    )

    assert await web.mirror_view(direct) == {
        "deliverable": True,
        "platform": "telegram",
        "target": "Telegram · direct chat",
        "reason": None,
        "undelivered": [],
    }
    view = await web.mirror_view(topic)
    assert view["deliverable"] is True
    assert view["target"] == "Telegram · topic"

    # The list stays cheap: no mirror there.
    listing = (await web.client.get("/api/v1/chat/conversations")).json()
    assert all(c["channel_binding"]["mirror"] is None for c in listing["conversations"])


async def test_a_deleted_channel_still_reads_with_no_platform(env: ChannelEnv, web: _Web) -> None:
    resource, adapter = await _channel(env)
    conversation_id = await _conversation_from_chat(env, resource, adapter)
    await env.resources.delete(resource.uid, actor="cli")

    view = await web.mirror_view(conversation_id)

    assert view["deliverable"] is False
    assert view["reason"] == "channel_deleted"
    assert view["platform"] is None


def _binding(env: ChannelEnv, resource: Resource) -> ChannelBinding:
    binding = env.processor.binding(resource.uid)
    assert binding is not None
    return binding


async def _count(pending: Any, n: int) -> bool:
    return len(await pending) == n
