"""The file-backed store behind the web composer's uploads
(``infrastructure/chat/media_store.py``): what lands on disk, and that nothing
but an id it wrote itself ever resolves to a path."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coffer.infrastructure.chat.media_store import FileChatMediaStore, default_chat_media_dir


async def test_save_then_resolve_round_trips(tmp_path: Path) -> None:
    store = FileChatMediaStore(tmp_path / "chat-media")
    stored = await store.save(data=b"%PDF-1.7", filename="Report.PDF", mime="application/pdf")

    assert (stored.filename, stored.mime, stored.size) == ("Report.PDF", "application/pdf", 8)
    bytes_path = tmp_path / "chat-media" / f"{stored.id}.pdf"
    assert bytes_path.read_bytes() == b"%PDF-1.7"
    record = json.loads((tmp_path / "chat-media" / f"{stored.id}.json").read_text())
    assert record == {
        "filename": "Report.PDF",
        "mime": "application/pdf",
        "size": 8,
        "stored": f"{stored.id}.pdf",
    }
    resolved = await store.resolve(stored.id)
    assert resolved is not None
    assert (resolved.path, resolved.mime, resolved.filename) == (
        str(bytes_path),
        "application/pdf",
        "Report.PDF",
    )


async def test_an_odd_extension_is_not_kept_on_disk(tmp_path: Path) -> None:
    store = FileChatMediaStore(tmp_path)
    stored = await store.save(data=b"x", filename="weird.name with space", mime="text/plain")
    assert (tmp_path / stored.id).read_bytes() == b"x"


@pytest.mark.parametrize(
    "record",
    [
        "not json",
        json.dumps({"filename": "a", "mime": "text/plain"}),  # no "stored"
        json.dumps({"filename": "a", "mime": "text/plain", "stored": "../../etc/passwd"}),
        json.dumps({"filename": "a", "mime": "text/plain", "stored": "0" * 32 + "/x"}),
    ],
)
async def test_a_record_that_does_not_name_its_own_file_resolves_to_nothing(
    tmp_path: Path, record: str
) -> None:
    attachment_id = "0" * 32
    (tmp_path / f"{attachment_id}.json").write_text(record)
    assert await FileChatMediaStore(tmp_path).resolve(attachment_id) is None


async def test_unknown_malformed_or_orphaned_ids_resolve_to_nothing(tmp_path: Path) -> None:
    store = FileChatMediaStore(tmp_path)
    stored = await store.save(data=b"x", filename="a.txt", mime="text/plain")
    assert await store.resolve("f" * 32) is None
    assert await store.resolve("../" + stored.id) is None
    (tmp_path / f"{stored.id}.txt").unlink()  # bytes gone, record left behind
    assert await store.resolve(stored.id) is None


async def test_prune_deletes_by_age(tmp_path: Path) -> None:
    store = FileChatMediaStore(tmp_path)
    old = await store.save(data=b"o", filename="o.txt", mime="text/plain")
    new = await store.save(data=b"n", filename="n.txt", mime="text/plain")
    now = datetime.now(tz=UTC)
    ts = (now - timedelta(days=30, seconds=1)).timestamp()
    for name in (f"{old.id}.txt", f"{old.id}.json"):
        os.utime(tmp_path / name, (ts, ts))

    deleted = store.prune(now)

    assert sorted(deleted) == sorted(
        [str(tmp_path / f"{old.id}.txt"), str(tmp_path / f"{old.id}.json")]
    )
    assert await store.resolve(new.id) is not None


def test_prune_of_a_missing_dir_is_a_no_op(tmp_path: Path) -> None:
    assert FileChatMediaStore(tmp_path / "never-created").prune(datetime.now(tz=UTC)) == []


def test_default_dir_is_beside_channel_media_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_chat_media_dir() == tmp_path / ".coffer" / "chat-media"
