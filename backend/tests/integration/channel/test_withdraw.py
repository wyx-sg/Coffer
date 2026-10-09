"""Withdraw a bot reply on the owner's command (spec channels "Withdraw a bot reply
on the owner's command"): ``/del``, the 🗑 button, the reply ledger behind them."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.channel.store_ports import ReplyRecord
from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.infrastructure.channel.persistence import ChannelReplyRepo
from coffer.infrastructure.persistence.engine import session_maker

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, tap_event, wait_until

_OWNER = "owner-1"
_GROUP = "grp-1"


class _ChunkingAdapter(FakeChannelAdapter):
    """A transport that cuts every reply into two messages and reports both ids."""

    async def send_text(  # type: ignore[override]
        self,
        chat_id: str,
        markdown: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        **kwargs: Any,
    ) -> SentMessage:
        first = await super().send_text(chat_id, markdown, buttons=None, **kwargs)
        last = await super().send_text(chat_id, "(2/2)", buttons=buttons, **kwargs)
        return SentMessage(last.message_id, (first.message_id, last.message_id))


def _withdrawing(cls: type[FakeChannelAdapter] = FakeChannelAdapter) -> FakeChannelAdapter:
    return cls(supports_buttons=True, withdraw_window_hours=48, withdraw_removes=True)


def _ledger(env: ChannelEnv) -> ChannelReplyRepo:
    return ChannelReplyRepo(session_maker(env.engine))


async def _group_reply(env: ChannelEnv, adapter: FakeChannelAdapter) -> tuple[str, ReplyRecord]:
    """Pair, let the owner @mention the bot in a group, and return the channel uid and
    the reply the bot recorded."""
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id=_OWNER)
    await env.processor.on_message(
        inbound(
            "tg", _GROUP, "hello", chat_kind="group", sender_id=_OWNER, platform_message_id="q1"
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())
    record = await _wait_record(env, resource.uid)
    return resource.uid, record


async def _wait_record(env: ChannelEnv, uid: str, chat: str = _GROUP) -> ReplyRecord:
    ledger = _ledger(env)
    found: list[ReplyRecord] = []

    async def _has() -> bool:
        record = await ledger.latest(uid, chat, None)
        if record is not None:
            found[:] = [record]
        return record is not None

    for _ in range(200):
        if await _has():
            return found[0]
        await asyncio.sleep(0.02)
    raise AssertionError("no reply was recorded")


@pytest.mark.acceptance(
    spec="channels", scenario="a group reply carries a trash button the owner can tap"
)
async def test_the_group_reply_carries_a_trash_button_and_the_owner_tap_withdraws_it(
    env: ChannelEnv,
) -> None:
    adapter = _withdrawing()
    uid, record = await _group_reply(env, adapter)

    reply_index = adapter.texts().index("Hello world")
    buttons = adapter.sent_buttons[reply_index]
    assert [b.label for b in buttons] == ["🗑"]
    assert buttons[0].value == f"del:{record.reply_id}"

    await env.processor.on_callback(
        tap_event("tg", _GROUP, buttons[0].value, chat_kind="group", sender_id=_OWNER)
    )

    assert [m for _c, m, _k in adapter.withdrawn] == list(record.message_ids)
    assert await _ledger(env).get(record.reply_id) is None
    assert uid


@pytest.mark.acceptance(spec="channels", scenario="nobody but the owner can withdraw a reply")
async def test_a_tap_or_command_from_anyone_else_withdraws_nothing_and_says_nothing(
    env: ChannelEnv,
) -> None:
    adapter = _withdrawing()
    _uid, record = await _group_reply(env, adapter)
    sent_before = len(adapter.sent)

    await env.processor.on_callback(
        tap_event("tg", _GROUP, f"del:{record.reply_id}", chat_kind="group", sender_id="intruder")
    )
    await env.processor.on_message(
        inbound(
            "tg",
            _GROUP,
            "/del",
            chat_kind="group",
            sender_id="intruder",
            quoted_message_id=record.message_ids[0],
            platform_message_id="d1",
        )
    )

    assert adapter.withdrawn == []
    assert await _ledger(env).get(record.reply_id) is not None
    # The command from a stranger meets the ordinary refusal; the tap meets silence.
    assert all("🗑" not in text for text in adapter.texts()[sent_before:])


@pytest.mark.acceptance(spec="channels", scenario="/del with a quote withdraws that whole reply")
@pytest.mark.acceptance(spec="channels", scenario="a withdrawal is audited without content")
async def test_del_with_a_quote_withdraws_every_message_of_that_reply(env: ChannelEnv) -> None:
    adapter = _withdrawing(_ChunkingAdapter)
    _uid, record = await _group_reply(env, adapter)
    assert len(record.message_ids) == 2

    await env.processor.on_message(
        inbound(
            "tg",
            _GROUP,
            "/del",
            chat_kind="group",
            sender_id=_OWNER,
            quoted_message_id=record.message_ids[0],
            platform_message_id="d1",
        )
    )

    assert [m for _c, m, _k in adapter.withdrawn] == list(record.message_ids)
    assert await _ledger(env).get(record.reply_id) is None
    # The owner's own command goes too, on a transport that removes messages.
    assert (_GROUP, "d1") in adapter.deleted
    entries = await env.audit_entries("channel_reply_withdrawn")
    assert [e.actor for e in entries] == ["owner"]
    assert entries[0].details["messages"] == 2
    assert set(entries[0].details) == {"chat_id", "messages", "via"}  # ids and counts, no text


@pytest.mark.acceptance(spec="channels", scenario="a long reply is withdrawn in every part")
async def test_a_reply_and_its_uploaded_file_are_withdrawn_together(env: ChannelEnv) -> None:
    adapter = _withdrawing()
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id=_OWNER)
    ledger = _ledger(env)
    await ledger.add(
        ReplyRecord(
            reply_id="r1",
            resource_uid=resource.uid,
            chat_id=_GROUP,
            thread_id="",
            chat_kind="group",
            message_ids=("a", "b", "file-1"),
            sent_at=datetime.now(tz=UTC),
        )
    )

    await env.processor.on_message(
        inbound(
            "tg", _GROUP, "/del", chat_kind="group", sender_id=_OWNER, quoted_message_id="file-1"
        )
    )

    assert [m for _c, m, _k in adapter.withdrawn] == ["a", "b", "file-1"]


@pytest.mark.acceptance(spec="channels", scenario="/del without a quote withdraws the latest reply")
async def test_del_without_a_quote_withdraws_only_the_latest_reply(env: ChannelEnv) -> None:
    adapter = _withdrawing()
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id=_OWNER)
    ledger = _ledger(env)
    now = datetime.now(tz=UTC)
    for reply_id, ids, age in (("old", ("o1",), 5), ("new", ("n1", "n2"), 1)):
        await ledger.add(
            ReplyRecord(
                reply_id=reply_id,
                resource_uid=resource.uid,
                chat_id=_GROUP,
                thread_id="",
                chat_kind="group",
                message_ids=ids,
                sent_at=now - timedelta(minutes=age),
            )
        )

    await env.processor.on_message(
        inbound("tg", _GROUP, "/del", chat_kind="group", sender_id=_OWNER)
    )

    assert [m for _c, m, _k in adapter.withdrawn] == ["n1", "n2"]
    assert await ledger.get("old") is not None
    assert await ledger.get("new") is None


@pytest.mark.acceptance(spec="channels", scenario="a direct chat reply carries no trash button")
async def test_a_direct_reply_has_no_button_and_del_still_withdraws_it(env: ChannelEnv) -> None:
    adapter = _withdrawing()
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner")
    await env.processor.on_message(inbound("tg", "owner", "hello"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert adapter.sent_buttons[adapter.texts().index("Hello world")] == []
    record = await _wait_record(env, resource.uid, "owner")

    await env.processor.on_message(inbound("tg", "owner", "/del", platform_message_id="d1"))

    assert [m for _c, m, _k in adapter.withdrawn] == list(record.message_ids)


@pytest.mark.acceptance(
    spec="channels", scenario="a reply past the platform window is reported privately"
)
async def test_a_reply_past_the_window_is_told_to_the_owner_alone(env: ChannelEnv) -> None:
    adapter = _withdrawing()
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id=_OWNER)
    await _ledger(env).add(
        ReplyRecord(
            reply_id="stale",
            resource_uid=resource.uid,
            chat_id=_GROUP,
            thread_id="",
            chat_kind="group",
            message_ids=("s1",),
            sent_at=datetime.now(tz=UTC) - timedelta(hours=49),
        )
    )

    await env.processor.on_message(
        inbound("tg", _GROUP, "/del", chat_kind="group", sender_id=_OWNER, quoted_message_id="s1")
    )

    assert adapter.withdrawn == []
    told = [(chat, text) for chat, text in adapter.sent if "no longer be withdrawn" in text]
    assert [chat for chat, _t in told] == ["owner"]
    assert all(chat != _GROUP for chat, _t in adapter.sent)


async def test_del_with_nothing_on_record_says_so(env: ChannelEnv) -> None:
    adapter = _withdrawing()
    resource = await env.register_channel("tg")
    env.bind(resource, adapter)
    await env.pair(resource, "owner")

    await env.processor.on_message(inbound("tg", "owner", "/del"))

    assert adapter.withdrawn == []
    assert any("no reply of mine" in text for text in adapter.texts())


@pytest.mark.acceptance(spec="channels", scenario="replies are remembered across a restart")
async def test_the_ledger_finds_a_reply_by_any_message_and_prunes_the_old(
    env: ChannelEnv,
) -> None:
    now = datetime.now(tz=UTC)
    first = _ledger(env)
    await first.add(ReplyRecord("fresh", "uid", "c", "", "group", ("m1", "m2"), now))
    await first.add(
        ReplyRecord("ancient", "uid", "c", "", "group", ("m0",), now - timedelta(days=30))
    )

    reopened = _ledger(env)  # a new repo over the same database: the restart

    found = await reopened.find_by_message("uid", "c", "m2")
    assert found is not None and found.reply_id == "fresh"
    assert found.message_ids == ("m1", "m2")
    assert await reopened.prune(now - timedelta(days=8)) == 1
    assert await reopened.get("ancient") is None


@pytest.mark.acceptance(
    spec="channels",
    scenario="a direct-chat reply the transport cannot take back is not recorded",
)
async def test_a_direct_reply_a_transport_cannot_withdraw_is_not_recorded(
    env: ChannelEnv,
) -> None:
    # SeaTalk-shaped: it can rewrite a card for 168 hours but cannot delete, so a
    # plain text reply in a direct chat is beyond its reach.
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_buttons=True,
        withdraw_window_hours=168,
        withdraw_removes=False,
    )
    resource = await env.register_channel("st")
    env.bind(resource, adapter)
    await env.pair(resource, "owner")

    await env.processor.on_message(inbound("st", "owner", "hello"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    await asyncio.sleep(0.05)
    assert await _ledger(env).latest(resource.uid, "owner", None) is None

    await env.processor.on_message(inbound("st", "owner", "/del"))

    assert adapter.withdrawn == []
    assert any("no reply of mine" in text for text in adapter.texts())
