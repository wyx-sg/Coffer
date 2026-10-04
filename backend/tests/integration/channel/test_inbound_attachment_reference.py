"""An inbound attachment reaches the turn as a reference, and no message row records it.

See spec channels "Hand inbound attachments to the turn as references" and chat
"Let the agent's own session hold the conversation". The channel's media dir holds
the bytes; the turn carries only path, mime and filename, and Coffer keeps no
message to hold them in.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from sqlalchemy import text

from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted

from .conftest import ChannelEnv, inbound, wait_until

_BYTES = b"\x89PNG\r\n\x1a\nFAKE-IMAGE-BYTES"


class _Recorder:
    """A scripted agent that records the prompt and attachments its turn was given."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.attachments: list[tuple[Attachment, ...]] = []

    async def run_turn(
        self, prompt: str, attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        self.prompts.append(prompt)
        self.attachments.append(tuple(attachments))
        return self._events()

    async def _events(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="Hello world")
        yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


async def _run_image_turn(env: ChannelEnv, tmp_path: Path) -> tuple[_Recorder, Path]:
    recorder = _Recorder()
    env.provider.adapter = recorder
    _resource, adapter = await env.paired_channel()
    image = tmp_path / "photo.png"
    image.write_bytes(_BYTES)

    await env.processor.on_message(
        inbound(
            "tg",
            "owner",
            "what is this?",
            attachments=[
                InboundAttachment(path=str(image), mime="image/png", filename="photo.png")
            ],
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())
    return recorder, image


@pytest.mark.acceptance(
    spec="channels", scenario="an inbound attachment reaches the turn as a reference"
)
async def test_an_inbound_attachment_reaches_the_turn_as_a_reference(
    env: ChannelEnv, tmp_path: Path
) -> None:
    recorder, image = await _run_image_turn(env, tmp_path)

    # The adapter is given path, mime and filename; the bytes stay in the media dir.
    assert recorder.attachments == [
        (Attachment(path=str(image), mime="image/png", filename="photo.png"),)
    ]
    assert image.read_bytes() == _BYTES
    assert all("FAKE-IMAGE-BYTES" not in p for p in recorder.prompts)
    # No message row records it.
    async with env.engine.connect() as conn:
        tables = {
            r[0]
            for r in await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert "chat_messages" not in tables


@pytest.mark.acceptance(
    spec="chat", scenario="a turn's attachment reaches the adapter without a stored message"
)
async def test_a_turns_attachment_reaches_the_adapter_without_a_stored_message(
    env: ChannelEnv, tmp_path: Path
) -> None:
    recorder, image = await _run_image_turn(env, tmp_path)

    [(received,)] = recorder.attachments
    assert (received.path, received.mime, received.filename) == (
        str(image),
        "image/png",
        "photo.png",
    )
    # The index row holds the conversation only: no table carries the attachment.
    async with env.engine.connect() as conn:
        for (table,) in await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ):
            rows = (await conn.execute(text(f'SELECT * FROM "{table}"'))).fetchall()
            assert not any("photo.png" in str(v) for row in rows for v in row), table
