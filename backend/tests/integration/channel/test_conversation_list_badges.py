"""The Conversations list's source badge, directory and Running mark (spec chat
"Show channel conversations on the Conversations page").

Driven through the real conversation routes on the channel fixture's real chat
platform and channel core, with ``ChannelPlaces`` wired as the composition root
wires it: each row says which channel, chat and thread it came from, its
directory and native session id, and whether a turn is running — and the
listing reads the same number of queries whatever the page holds.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import event

from coffer.application.channel.places import ChannelPlaces
from coffer.application.chat import turn_state
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.resource import Resource
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_channel_places,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.dependencies import get_resource_service

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until

_TOKEN = "badge-token"


@pytest_asyncio.fixture
async def client(env: ChannelEnv) -> AsyncIterator[httpx.AsyncClient]:
    places = ChannelPlaces(threads=env.threads)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(conversation_router)
    app.dependency_overrides[get_chat_service] = lambda: env.chat
    app.dependency_overrides[get_turn_orchestrator] = lambda: env.orchestrator
    app.dependency_overrides[get_resource_service] = lambda: env.resources
    app.dependency_overrides[get_channel_places] = lambda: places
    set_active_token(_TOKEN)
    c = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Coffer-Token": _TOKEN},
    )
    try:
        yield c
    finally:
        await c.aclose()
        set_active_token(None)


async def _listed(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    resp = await client.get("/api/v1/chat/conversations")
    assert resp.status_code == 200, resp.text
    return {c["id"]: c for c in resp.json()["conversations"]}


async def _seatalk(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel(
        "st",
        ref="channel/st/app-secret",
        config={
            "channel_type": "seatalk",
            "app_id": "app-1",
            "app_secret_ref": "channel/st/app-secret",
        },
    )
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_edit=False, direct_threads_are_replies=True)
    )
    await env.pair(resource, "owner", sender_id="owner-1")
    return resource, adapter


async def _opened_by(
    env: ChannelEnv,
    resource: Resource,
    adapter: FakeChannelAdapter,
    *,
    chat_id: str = "owner",
    thread_id: str = "",
    chat_kind: str = "direct",
) -> str:
    """A conversation the chat opened with one message and its answer."""
    before = len(adapter.sent)
    await env.send(
        inbound(
            resource.name,
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
    await wait_until(lambda: not turn_state.is_running(conversation_id))
    return conversation_id


@contextmanager
def _running(conversation_id: str) -> Iterator[None]:
    """Hold the conversation as though a turn were in flight."""
    state = turn_state.state_for(conversation_id)
    state.active = turn_state.ActiveTurn()
    try:
        yield
    finally:
        state.active = None
        turn_state.evict_if_idle(conversation_id)


@contextmanager
def _counting_queries(env: ChannelEnv) -> Iterator[list[str]]:
    statements: list[str] = []

    def _record(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(env.engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(env.engine.sync_engine, "before_cursor_execute", _record)


@pytest.mark.acceptance(spec="chat", scenario="a row names the chat and thread it came from")
async def test_each_row_names_its_source_chat_and_directory(
    env: ChannelEnv, client: httpx.AsyncClient
) -> None:
    resource, adapter = await _seatalk(env)
    dm = await _opened_by(env, resource, adapter)
    group_thread = await _opened_by(
        env, resource, adapter, chat_id="grp-1", thread_id="th-1", chat_kind="group"
    )
    await env.chat.set_agent_config(dm, AgentConfig(cwd="/work/app", session_id="sess-9"))
    # A conversation no channel owns is not on the list.
    orphan = await env.chat.create_conversation(agent_key="builtin")

    rows = await _listed(client)

    assert orphan.id not in rows
    assert set(rows) == {dm, group_thread}
    assert (rows[dm]["cwd"], rows[dm]["session_id"]) == ("/work/app", "sess-9")
    assert rows[dm]["running"] is False
    assert "preview" not in rows[dm] and "archived_at" not in rows[dm]

    dm_binding = rows[dm]["channel_binding"]
    assert dm_binding["platform"] == "seatalk"
    assert dm_binding["channel"] == "st"
    assert dm_binding["place"] == {
        "chat_kind": "direct",
        "thread": False,
        "parallel_mark": None,
        "chat_name": None,
    }

    thread_place = rows[group_thread]["channel_binding"]["place"]
    assert thread_place["chat_kind"] == "group"
    assert thread_place["thread"] is True
    assert thread_place["parallel_mark"] is None


async def test_a_parallel_thread_carries_its_mark(
    env: ChannelEnv, client: httpx.AsyncClient
) -> None:
    resource, adapter = await _seatalk(env)
    await _opened_by(env, resource, adapter)
    await env.processor.on_message(
        inbound(resource.name, "owner", "/thread deploy check", sender_id="owner-1")
    )
    parallel = await env.active_conversation(resource, "owner", "t1")
    assert parallel is not None

    place = (await _listed(client))[parallel]["channel_binding"]["place"]

    assert place["parallel_mark"] == "🧵#1 deploy check"
    assert place["chat_kind"] == "direct"
    assert place["thread"] is True


async def test_a_running_turn_is_marked(env: ChannelEnv, client: httpx.AsyncClient) -> None:
    resource, adapter = await _seatalk(env)
    dm = await _opened_by(env, resource, adapter)

    with _running(dm):
        row = (await _listed(client))[dm]
        single = (await client.get(f"/api/v1/chat/conversations/{dm}")).json()

    assert row["running"] is True
    assert single["running"] is True
    assert (await _listed(client))[dm]["running"] is False


async def test_a_deleted_channel_leaves_no_platform(
    env: ChannelEnv, client: httpx.AsyncClient
) -> None:
    resource, adapter = await _seatalk(env)
    dm = await _opened_by(env, resource, adapter)
    await env.resources.delete(resource.uid, actor="test")

    binding = (await _listed(client))[dm]["channel_binding"]

    assert binding["channel_uid"] == resource.uid
    assert binding["channel"] is None
    assert binding["platform"] is None


async def test_the_listing_reads_a_constant_number_of_queries(
    env: ChannelEnv, client: httpx.AsyncClient
) -> None:
    resource, adapter = await _seatalk(env)
    await _opened_by(env, resource, adapter)
    with _counting_queries(env) as one_row:
        assert len(await _listed(client)) == 1

    await _opened_by(env, resource, adapter, chat_id="grp-1", thread_id="th-1", chat_kind="group")
    await _opened_by(env, resource, adapter, chat_id="grp-1", thread_id="th-2", chat_kind="group")
    with _counting_queries(env) as three_rows:
        assert len(await _listed(client)) == 3

    assert one_row, "the listener saw the listing's queries"
    assert len(three_rows) == len(one_row)
