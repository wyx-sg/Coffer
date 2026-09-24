"""SeaTalk-specific acceptance scenarios that need the real channel core.

Registration scenarios run through the real ``ResourceService`` with the real
channel kind (config schema + credential probing). The card and thread
scenarios bind the REAL ``SeaTalkAdapter`` — talking to the in-process
``FakeSeaTalk`` Open API — into the real ``InboundProcessor``, so what is
asserted is the wire traffic SeaTalk would actually receive.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.errors import ConfigValidationError
from coffer.infrastructure.channel.seatalk_ws import SeaTalkWebSocketConnector
from tests.integration.infrastructure.channel.conftest import (
    FakeSeaTalk,
    RecordingCallbacks,
    make_seatalk_adapter,
)

from .conftest import DEFAULT_AGENT_KEY, ChannelEnv, tap_event, wait_until
from .fake_seatalk_sdk import build_fake_sdk, deliver, envelope, hold

_APP_SECRET_REF = "channel/st/app-secret"


async def _seatalk_config(env: ChannelEnv, **overrides: Any) -> dict[str, Any]:
    env.keyring.set(_APP_SECRET_REF, "app-secret-value")
    config: dict[str, Any] = {
        "channel_type": "seatalk",
        "app_id": "app-1",
        "app_secret_ref": _APP_SECRET_REF,
        "default_agent": await env.agent_uid(DEFAULT_AGENT_KEY),
    }
    config.update(overrides)
    return {k: v for k, v in config.items() if v is not None}


# -- registration ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a seatalk channel without an app id or secret reference is refused",
)
async def test_app_id_and_app_secret_ref_are_both_required(env: ChannelEnv) -> None:
    for missing in ("app_id", "app_secret_ref"):
        config = await _seatalk_config(env)
        del config[missing]
        with pytest.raises(ConfigValidationError):
            await env.resources.register(kind="channel", name="st", config=config, actor="test")
        assert await env.resources.list(kind="channel") == []

    resource = await env.resources.register(
        kind="channel", name="st", config=await _seatalk_config(env), actor="test"
    )
    assert resource.config["app_id"] == "app-1"
    assert resource.config["app_secret_ref"] == _APP_SECRET_REF
    # The secret itself never enters the stored configuration — only its ref.
    assert "app-secret-value" not in repr(resource.config)
    # And nothing about an inbound transport is asked for or stored.
    for key in ("delivery", "signing_secret_ref", "public_base_url", "tunnel_token_ref"):
        assert key not in resource.config


# -- the real adapter bound into the core ------------------------------------------


async def _bound_seatalk(env: ChannelEnv, fake: FakeSeaTalk, *, owner: str = "emp-1") -> Any:
    resource = await env.resources.register(
        kind="channel", name="st", config=await _seatalk_config(env), actor="test"
    )
    adapter = make_seatalk_adapter(fake)
    env.bind(resource, adapter)  # type: ignore[arg-type]
    await env.pair(resource, owner, sender_id=owner)
    return resource, adapter


def _card_sends(fake: FakeSeaTalk) -> list[dict[str, Any]]:
    return [
        body["message"]
        for body, _auth in fake.single_chat_calls
        if body["message"].get("tag") == "interactive_message"
    ]


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a refused card update drops a choice rewrite but reposts a page turn",
)
async def test_a_refused_card_update_drops_a_rewrite_but_reposts_a_page(env: ChannelEnv) -> None:
    fake = FakeSeaTalk()
    updates: list[dict[str, Any]] = []

    async def refuse_update(request: Request) -> JSONResponse:
        # How SeaTalk answers an update outside its window (older than 7 days,
        # or not this bot's card): a non-zero code.
        updates.append(await request.json())
        return JSONResponse(content={"code": 7001, "message": "message cannot be updated"})

    fake.app.post("/messaging/v2/update")(refuse_update)
    env.model_suggestions.add(DEFAULT_AGENT_KEY, [f"model-{i}" for i in range(12)])
    _resource, adapter = await _bound_seatalk(env, fake)
    try:
        # A choice: the model is applied, the in-place rewrite is refused, and
        # no replacement card is posted for it.
        await env.processor.on_callback(
            tap_event("st", "emp-1", "model:model-5", sender_id="emp-1", platform_message_id="c1")
        )
        await wait_until(lambda: len(updates) == 1)
        await wait_until(
            lambda: any("model-5" in str(body["message"]) for body, _ in fake.single_chat_calls)
        )
        assert _card_sends(fake) == []

        # A page turn: the rewrite is refused too, so the page arrives as a
        # fresh card the user can still use.
        await env.processor.on_callback(
            tap_event("st", "emp-1", "page:model:1", sender_id="emp-1", platform_message_id="c1")
        )
        await wait_until(lambda: len(_card_sends(fake)) == 1)
    finally:
        await adapter.stop()
    assert len(updates) == 2
    [card] = _card_sends(fake)
    assert "Page 2/" in str(card)


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a main-chat mention roots a new thread at itself"
)
async def test_a_main_chat_mention_is_answered_in_a_thread_rooted_at_it(env: ChannelEnv) -> None:
    fake = FakeSeaTalk()
    _resource, adapter = await _bound_seatalk(env, fake, owner="emp-2")
    recorder = RecordingCallbacks()
    await adapter.start(recorder.as_callbacks())
    try:
        await adapter.handle_event(
            {
                "event_type": "new_mentioned_message_received_from_group_chat",
                "timestamp": 1718000000,
                "event": {
                    "group_id": "gid-1",
                    "message": {
                        "message_id": "gm-1",
                        "thread_id": "",
                        "sender": {
                            "seatalk_id": "st-1",
                            "employee_code": "emp-2",
                            "email": "owner@example.com",
                            "sender_type": 1,
                        },
                        "tag": "text",
                        "text": {
                            "plain_text": "@Bot hi",
                            "mentioned_list": [{"username": "Bot", "seatalk_id": "bot-1"}],
                        },
                    },
                },
            }
        )
        [msg] = recorder.messages
        assert msg.thread_id == "gm-1"

        await env.processor.on_message(msg)

        def replied() -> bool:
            return any(
                "Hello world" in str(body)
                for _s, body in fake.init_stream_calls + fake.update_stream_calls
            ) or any("Hello world" in str(body) for body, _ in fake.group_chat_calls)

        await wait_until(replied)
    finally:
        await adapter.stop()

    # Every group post the turn made went into the thread rooted at gm-1.
    group_posts = [body for _s, body in fake.init_stream_calls] + [
        body for body, _ in fake.group_chat_calls
    ]
    assert group_posts
    assert all(body["message"].get("thread_id") == "gm-1" for body in group_posts)
    assert fake.single_chat_calls == []
    # The thread holds only the @mention itself, so no history is read.
    assert fake.thread_calls == []


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="a websocket channel receives an event with no public url"
)
async def test_an_event_pushed_down_the_socket_drives_a_turn(env: ChannelEnv) -> None:
    """End to end over the one inbound transport: a channel configured with
    nothing but its app credentials, the fake SDK pushing a DM down the held
    connection, and the real adapter and processor answering it."""
    fake = FakeSeaTalk()
    resource, adapter = await _bound_seatalk(env, fake, owner="emp-1")
    assert {"app_id", "app_secret_ref"} <= set(resource.config)
    for key in ("delivery", "signing_secret_ref", "public_base_url", "tunnel_token_ref"):
        assert key not in resource.config
    await adapter.start(
        AdapterCallbacks(
            on_message=env.processor.on_message,
            on_callback=env.processor.on_callback,
            on_lifecycle=env.processor.on_lifecycle,
            on_stop=env.processor.on_stop,
        )
    )
    sdk = build_fake_sdk()
    sdk.plan[:] = [deliver(envelope()), hold()]

    async def ingest(channel_uid: str, payload: dict[str, Any]) -> None:
        # What ChannelService.ingest_event does once it has found the adapter.
        assert channel_uid == resource.uid
        await adapter.handle_event(payload)

    connector = SeaTalkWebSocketConnector(
        resource.uid,
        "app-1",
        "app-secret-value",
        ingest=ingest,
        loader=lambda: sdk.module,
        backoff_initial=0.01,
        backoff_max=0.04,
        kick_backoff=60.0,
        join_timeout=2.0,
    )
    await connector.start()
    try:

        def replied() -> bool:
            return any(
                "Hello world" in str(body)
                for _s, body in fake.init_stream_calls + fake.update_stream_calls
            ) or any("Hello world" in str(body) for body, _ in fake.single_chat_calls)

        await wait_until(replied, message="the pushed event never drove a turn")
        assert connector.state() == ("connected", None)
        assert sdk.connects == [("app-1", "app-secret-value")]
    finally:
        await connector.stop()
        await adapter.stop()
