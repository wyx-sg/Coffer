"""FR-033 — inbound attachments persisted as references + re-materialised.

Covers the elegant seam: the channel turn persists an ``AttachmentBlock`` into
the user message (single source of truth); the turn task derives the adapter's
attachments by reading them back from history's last user message (not a
threaded param); the wire view exposes filename/mime but never the local path;
and the media-dir prune ages files out by mtime.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.message import AttachmentBlock, Role, TextBlock
from coffer.infrastructure.channel.media_retention import prune_media_dir
from coffer.surfaces.http.chat.conversation_routes import _block_out

from .conftest import FakeAgentAdapter
from .test_turn_orchestrator_with_fake_adapter import drain_queue, make_orchestrator

_IMG = Attachment(path="/tmp/coffer-media/abc.jpg", mime="image/jpeg", filename="photo.jpg")


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="an inbound attachment is persisted as a reference on the user message",
)
@pytest.mark.asyncio
async def test_channel_turn_persists_attachment_block() -> None:
    adapter = FakeAgentAdapter([])
    orchestrator, _conv, _msg, _audit, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "look", attachments=[_IMG])
    await drain_queue(queue)

    history = await orchestrator._chat.list_messages(conv.id)
    user_msg = next(m for m in history if m.role is Role.USER)
    # Text first, then the reference — bytes never enter the DB.
    assert isinstance(user_msg.content[0], TextBlock)
    blocks = [b for b in user_msg.content if isinstance(b, AttachmentBlock)]
    assert blocks == [
        AttachmentBlock(path=_IMG.path, mime=_IMG.mime, filename=_IMG.filename),
    ]


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a later turn re-materialises the attachment from history",
)
@pytest.mark.asyncio
async def test_turn_re_materialises_attachment_from_history() -> None:
    adapter = FakeAgentAdapter([])
    orchestrator, _conv, _msg, _audit, _prov = make_orchestrator(adapter=adapter)
    conv = await orchestrator._chat.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "look", attachments=[_IMG])
    await drain_queue(queue)

    # The adapter received the attachment derived from history's last user
    # message — nothing is threaded down from the orchestrator any more.
    assert adapter.recorded_attachments[0] == [_IMG]


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="the message API exposes an attachment block without leaking the path",
)
def test_attachment_block_out_omits_path() -> None:
    out = _block_out(
        AttachmentBlock(path="/secret/on/disk.jpg", mime="image/jpeg", filename="p.jpg")
    )
    assert out.type == "attachment"
    assert out.filename == "p.jpg"
    assert out.mime == "image/jpeg"
    dumped = out.model_dump()
    assert "path" not in dumped
    assert "/secret/on/disk.jpg" not in dumped.values()


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="the media dir prune deletes stale files and keeps fresh ones",
)
def test_media_dir_prune_ages_out_by_mtime(tmp_path: object) -> None:
    import os

    media_dir = tmp_path / "channel-media"  # type: ignore[operator]
    media_dir.mkdir()
    now = datetime(2026, 7, 9, tzinfo=UTC)
    stale = media_dir / "old.jpg"
    fresh = media_dir / "new.jpg"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"y")
    old_ts = (now - timedelta(days=31)).timestamp()
    fresh_ts = (now - timedelta(days=1)).timestamp()
    os.utime(stale, (old_ts, old_ts))
    os.utime(fresh, (fresh_ts, fresh_ts))

    deleted = prune_media_dir(media_dir, max_age_days=30, now=now)  # type: ignore[arg-type]

    assert deleted == [str(stale)]
    assert not stale.exists()
    assert fresh.exists()
