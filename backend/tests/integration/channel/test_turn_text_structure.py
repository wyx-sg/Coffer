"""The text a channel turn hands the agent, end to end through the REAL SeaTalk
adapter: a forwarded record, then the owner's own words, then a photo — one burst,
one turn (spec channels "Take a burst of messages as one turn", "Flatten forwarded
chat records into the turn", "Hand inbound attachments to the turn as references").

Every part sits in its own role block with an end line, the record's image points
at the attachment it was downloaded as, and the owner's photo is told apart from
the record's.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from coffer.application.channel import inbound_burst
from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.chat.attachment import Attachment, attachments_block
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.infrastructure.chat.codex_stream import attachment_note
from tests.integration.infrastructure.channel.conftest import FakeSeaTalk, make_seatalk_adapter

from .conftest import DEFAULT_AGENT_KEY, ChannelEnv, uid_of, wait_until

_SENT = 1792570500  # 2026-10-21 08:15 UTC
_FILE = "https://openapi.seatalk.io/messaging/v2/file"


class _Recorder:
    """A scripted agent that records the prompt and attachments of each turn."""

    def __init__(self) -> None:
        self.turns: list[tuple[str, tuple[Attachment, ...]]] = []

    async def run_turn(
        self, prompt: str, attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        self.turns.append((prompt, tuple(attachments)))
        return self._events()

    async def _events(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="Hello world")
        yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _dm(message_id: str, message: dict[str, Any], *, offset: int = 0) -> dict[str, Any]:
    return {
        "event_id": f"evt-{message_id}",
        "event_type": "message_from_bot_subscriber",
        "timestamp": _SENT + offset,
        "event": {
            "employee_code": "177203",
            "email": "yuxing.wu@sea.com",
            "message": {"message_id": message_id, **message},
        },
    }


def _leaf(tag: str, body: dict[str, Any], *, sent: int) -> dict[str, Any]:
    return {
        "tag": tag,
        tag: body,
        "sender": {"email": "xingz@sea.com"},
        "message_sent_time": sent,
    }


_RECORD = {
    "tag": "combined_forwarded_chat_history",
    "combined_forwarded_chat_history": {
        "content": [
            {
                "tag": "combined_forwarded_chat_history",
                "combined_forwarded_chat_history": {
                    "content": [
                        _leaf(
                            "text",
                            {"content": "[Tech] Buyer campaign resource optimisation"},
                            sent=_SENT - 3600,
                        ),
                        _leaf(
                            "text",
                            {"content": "背景\nBuyer team 的资源已经没有 budget 了。"},
                            sent=_SENT - 3540,
                        ),
                        _leaf("image", {"content": f"{_FILE}/rec1?seq=3"}, sent=_SENT - 3480),
                        # A voice note SeaTalk handed over with nothing to download.
                        _leaf("voice", {}, sent=_SENT - 3420),
                    ]
                },
            }
        ]
    },
}


async def _seatalk(env: ChannelEnv, fake: FakeSeaTalk, tmp_path: Path) -> Any:
    env.keyring.set("channel/st/app-secret", "app-secret-value")
    resource = await env.resources.register(
        kind="channel",
        name="st",
        config={
            "channel_type": "seatalk",
            "app_id": "app-1",
            "app_secret_ref": "channel/st/app-secret",
            "default_agent": await env.agent_uid(DEFAULT_AGENT_KEY),
        },
        actor="test",
    )
    adapter = make_seatalk_adapter(fake, media_dir=tmp_path)
    env.bind(resource, adapter)  # type: ignore[arg-type]
    binding = env.processor.binding(uid_of("st"))
    assert binding is not None
    # Real quiet windows, so the three messages become one burst.
    env.processor.bind(
        dataclasses.replace(binding, wait_after_text_seconds=0.3, wait_after_forward_seconds=0.3)
    )
    await env.pair(resource, "177203", sender_id="177203")
    await adapter.start(
        AdapterCallbacks(
            on_message=env.processor.on_message,
            on_callback=env.processor.on_callback,
            on_lifecycle=env.processor.on_lifecycle,
            on_stop=env.processor.on_stop,
        )
    )
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels", scenario="a forwarded record, the owner's words and a photo become one turn"
)
async def test_a_forward_then_words_then_a_photo_read_as_marked_blocks(
    env: ChannelEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 60.0)
    recorder = _Recorder()
    env.provider.adapter = recorder
    fake = FakeSeaTalk()
    resource, adapter = await _seatalk(env, fake, tmp_path)
    try:
        await adapter.handle_event(_dm("u-1", _RECORD))
        await adapter.handle_event(
            _dm("u-2", {"tag": "text", "text": {"content": "这个要做什么"}}, offset=20)
        )
        await adapter.handle_event(
            _dm("u-3", {"tag": "image", "image": {"content": f"{_FILE}/own1"}}, offset=21)
        )
        await wait_until(lambda: len(recorder.turns) == 1, timeout=5)
    finally:
        await adapter.stop()

    (prompt, attachments) = recorder.turns[0]
    # Every downloaded file, numbered across the turn in the order the text reads.
    assert [(a.number, a.source) for a in attachments] == [
        (1, "the forwarded record"),
        (2, "the user's message 2/2"),
    ]
    assert fake.file_downloads == ["rec1", "own1"]
    rec, own = attachments
    assert prompt == (
        "[Message origin]\n"
        "platform: seatalk\n"
        f'channel: "st" (id: {resource.uid})\n'
        "chat: direct (id: 177203)\n"
        "from: yuxing.wu@sea.com (id: 177203) · sent: 2026-10-21 08:15 UTC\n"
        "[End of message origin]\n"
        "\n"
        "[Forwarded chat record — forwarded by the user; written by others]\n"
        "xingz@sea.com · 2026-10-21 07:15 UTC: [Tech] Buyer campaign resource optimisation\n"
        "xingz@sea.com · 2026-10-21 07:16 UTC: 背景\n"
        "    Buyer team 的资源已经没有 budget 了。\n"
        "xingz@sea.com · 2026-10-21 07:17 UTC: [image] → attachment #1\n"
        "xingz@sea.com · 2026-10-21 07:18 UTC: [voice] unavailable — the model cannot read audio\n"
        "[End of forwarded chat record]\n"
        "\n"
        "[User message 1/2]\n"
        "这个要做什么\n"
        "[End of user message]\n"
        "\n"
        "[User message 2/2]\n"
        "(sent an image → attachment #2)\n"
        "[End of user message]"
    )
    # What a path-native agent then reads below it: each file by number and source.
    assert attachments_block([attachment_note(a) for a in attachments]) == (
        "[Attachments]\n"
        f"#1 from the forwarded record: photo.png (image, saved at {rec.path})\n"
        f"#2 from the user's message 2/2: photo.png (image, saved at {own.path})\n"
        "[End of attachments]"
    )
