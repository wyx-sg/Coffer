"""A channel answers every person paired to it, and nobody else (spec channels
"Gate inbound traffic on sender identity")."""

from __future__ import annotations

from coffer.infrastructure.channel.persistence import ChannelPeerRepo

from .conftest import ChannelEnv, inbound, wait_until


async def _pair_second_person(env: ChannelEnv, resource, chat: str, who: str) -> None:  # type: ignore[no-untyped-def]
    code, _ = env.pairing.issue(resource.uid)  # no ``replaces``: this adds a person
    await env.processor.on_message(inbound("tg", chat, code, sender_id=who, sender_display=who))


async def test_a_second_person_pairs_and_both_are_served_and_a_stranger_is_not(
    env: ChannelEnv,
) -> None:
    resource, adapter = await env.paired_channel("tg", chat_id="dm-a", sender_id="a")
    await _pair_second_person(env, resource, "dm-b", "b")

    assert await env.peers.sender_ids(resource.uid) == {"a", "b"}
    status = await env.service.status(resource.uid)
    assert [p.sender_id for p in status.people] == ["a", "b"]

    for chat, who in (("dm-a", "a"), ("dm-b", "b")):
        await env.processor.on_message(inbound("tg", chat, "hello", sender_id=who))
        await wait_until(
            lambda chat=chat: any(c == chat and t == "Hello world" for c, t in adapter.sent)
        )

    before = len(adapter.sent)
    await env.processor.on_message(inbound("tg", "dm-x", "let me in", sender_id="x"))
    assert len(adapter.sent) == before  # a stranger gets nothing

    # A group: either person may address the bot, a stranger is told once.
    await env.processor.on_message(
        inbound("tg", "grp", "@bot hi", chat_kind="group", sender_id="b", thread_id="t1")
    )
    await wait_until(
        lambda: any(r[0] == "grp" and r[1] == "Hello world" for r in adapter.sent_routed)
    )
    await env.processor.on_message(
        inbound("tg", "grp", "@bot hi", chat_kind="group", sender_id="x", thread_id="t2")
    )
    assert "owners can use it here" in adapter.sent[-1][1]


async def test_removing_one_person_leaves_the_other_and_the_last_may_go(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel("tg", chat_id="dm-a", sender_id="a")
    await _pair_second_person(env, resource, "dm-b", "b")
    await env.processor.on_message(
        inbound("tg", "grp", "@bot hi", chat_kind="group", sender_id="a", thread_id="t1")
    )
    assert await env.peers.get_by_chat(resource.uid, "grp") is not None

    await env.service.remove_person(resource.uid, "a", actor="test")

    # Their DM and the group they brought the bot into are gone; b is untouched.
    assert sorted(p.chat_id for p in await env.peers.list_by_resource(resource.uid)) == ["dm-b"]
    before = len(adapter.sent)
    await env.processor.on_message(inbound("tg", "dm-a", "still here?", sender_id="a"))
    assert len(adapter.sent) == before
    await env.processor.on_message(inbound("tg", "dm-b", "hello", sender_id="b"))
    await wait_until(lambda: any(c == "dm-b" and t == "Hello world" for c, t in adapter.sent))
    entries = await env.audit_entries("channel_person_removed", resource)
    assert [e.details["sender_id"] for e in entries] == ["a"]

    # Removing the last person leaves the channel unpaired, as every channel starts.
    await env.service.remove_person(resource.uid, "b", actor="test")
    assert await env.peers.owner_peer(resource.uid) is None
    assert (await env.service.status(resource.uid)).people == ()


async def test_the_people_survive_a_restart(env: ChannelEnv) -> None:
    resource, _ = await env.paired_channel("tg", chat_id="dm-a", sender_id="a")
    await _pair_second_person(env, resource, "dm-b", "b")

    reopened = ChannelPeerRepo()  # a fresh process reads the same vault document
    assert await reopened.sender_ids(resource.uid) == {"a", "b"}
