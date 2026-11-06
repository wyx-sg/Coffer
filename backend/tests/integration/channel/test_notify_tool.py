"""``coffer__channel_notify``: an agent sends the owner a message, and files, in
their direct chat (spec channels "Let an agent message the owner's direct
chat")."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.channel.notify_tool import OwnerNotifier, channel_notify_tool
from coffer.application.channel.ports import ChannelBinding

from .conftest import ChannelEnv, FakeChannelAdapter


async def _notifier(env: ChannelEnv, *names: str) -> tuple[OwnerNotifier, list[FakeChannelAdapter]]:
    adapters = []
    uids = []
    for name in names or ("st",):
        resource = await env.register_channel(name)
        adapter = env.bind(resource, FakeChannelAdapter())
        # The owner's direct chat is paired first; a group after it.
        await env.pair(resource, f"owner-{name}", sender_id="owner-1")
        await env.pair(resource, f"grp-{name}", sender_id="owner-1")
        adapters.append(adapter)
        uids.append(resource.uid)

    async def bindings() -> list[ChannelBinding]:
        out = [env.processor.binding(uid) for uid in uids]
        return [b for b in out if b is not None]

    return OwnerNotifier(bindings=bindings, peers=env.peers), adapters


@pytest.mark.acceptance(
    spec="channels", scenario="an agent in a terminal tells the owner it is done"
)
async def test_the_message_and_its_files_reach_the_owners_direct_chat(
    env: ChannelEnv, tmp_path: Any
) -> None:
    report = tmp_path / "report.md"
    report.write_text("# done")
    notifier, [adapter] = await _notifier(env)

    result = await notifier.notify({"text": "The migration finished.", "files": [str(report)]})

    assert result == {"sent": True, "channel": "st"}
    assert adapter.sent == [("owner-st", "The migration finished.")]
    assert [m[0] for m in adapter.media] == ["owner-st"]
    assert adapter.media[0][1] == str(report)


@pytest.mark.acceptance(spec="channels", scenario="several channels need one named")
async def test_several_paired_channels_need_one_named(env: ChannelEnv) -> None:
    notifier, adapters = await _notifier(env, "st", "tg")

    with pytest.raises(ValueError, match="pass `channel`"):
        await notifier.notify({"text": "hi"})

    await notifier.notify({"text": "hi", "channel": "tg"})
    assert adapters[0].sent == []
    assert adapters[1].sent == [("owner-tg", "hi")]


@pytest.mark.parametrize(
    "args",
    [{}, {"text": "  "}, {"text": "x" * 4001}, {"text": "hi", "files": ["relative.txt"]}],
)
async def test_bad_arguments_send_nothing(env: ChannelEnv, args: dict[str, Any]) -> None:
    notifier, [adapter] = await _notifier(env)

    with pytest.raises(ValueError):
        await notifier.notify(args)
    assert adapter.sent == []


async def test_no_paired_channel_says_where_to_set_one_up(env: ChannelEnv) -> None:
    async def none() -> list[ChannelBinding]:
        return []

    notifier = OwnerNotifier(bindings=none, peers=env.peers)
    with pytest.raises(ValueError, match="Channels page"):
        await notifier.notify({"text": "hi"})


def test_the_tool_is_offered_outside_turns_too() -> None:
    tool = channel_notify_tool(OwnerNotifier(bindings=None, peers=None))  # type: ignore[arg-type]
    assert tool.name == "channel_notify"
    assert tool.turn_scoped is False
    assert tool.input_schema["required"] == ["text"]
