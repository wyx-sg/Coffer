"""Paired people's pictures (spec channels "Show each paired person's platform
picture"): asked of the running adapter, cached a day, and every failure read
as "no picture" so the list keeps the person's initials."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.application.channel.avatars import (
    REFRESH_AFTER_SECONDS,
    RETRY_AFTER_SECONDS,
    Avatar,
    PersonAvatars,
    image_type,
)
from coffer.application.channel.store_ports import ChannelPeer
from coffer.infrastructure.channel.avatar_store import FileAvatarStore

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


class _Peers:
    def __init__(self, *senders: str) -> None:
        self.senders = list(senders)

    async def list_by_resource(self, resource_uid: str) -> list[ChannelPeer]:
        return [
            ChannelPeer(
                resource_uid=resource_uid,
                chat_id=s,
                display_name=s,
                paired_at=datetime(2026, 10, 1, tzinfo=UTC),
                sender_id=s,
            )
            for s in self.senders
        ]


class _Adapter:
    def __init__(self, answer: bytes | Exception | None) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def fetch_avatar(self, sender_id: str) -> bytes | None:
        self.asked.append(sender_id)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class _MemoryStore(FileAvatarStore):
    """The file store, with the fetch time taken from the test's clock."""

    def __init__(self, root: Path, clock: _Clock) -> None:
        super().__init__(root)
        self._clock = clock

    def write(self, channel_uid: str, sender_id: str, avatar: Avatar) -> None:
        super().write(channel_uid, sender_id, avatar)
        path = self._path(channel_uid, sender_id)
        os.utime(path, (self._clock.now, self._clock.now))


def _avatars(tmp_path: Path, adapter: object | None, *senders: str) -> tuple[PersonAvatars, _Clock]:
    clock = _Clock()
    return (
        PersonAvatars(
            store=_MemoryStore(tmp_path, clock),
            peers=_Peers(*senders),
            adapter_of=lambda uid: adapter,
            clock=clock,
        ),
        clock,
    )


@pytest.mark.acceptance(
    spec="channels", scenario="a paired person's picture is fetched once and kept a day"
)
async def test_fetches_once_then_serves_the_cache_until_a_day_has_passed(tmp_path: Path) -> None:
    adapter = _Adapter(_PNG)
    avatars, clock = _avatars(tmp_path, adapter, "ann")
    first = await avatars.get("ch", "ann")
    assert first == Avatar(data=_PNG, content_type="image/png")
    assert await avatars.get("ch", "ann") == first
    assert adapter.asked == ["ann"]
    # A day on, the platform is asked again and a changed picture replaces it.
    clock.now += REFRESH_AFTER_SECONDS + 1
    adapter.answer = _JPEG
    assert await avatars.get("ch", "ann") == Avatar(data=_JPEG, content_type="image/jpeg")
    assert adapter.asked == ["ann", "ann"]


@pytest.mark.acceptance(
    spec="channels", scenario="a person with no reachable picture keeps their initials"
)
async def test_a_refused_fetch_is_no_picture_and_is_not_retried_for_an_hour(
    tmp_path: Path,
) -> None:
    adapter = _Adapter(RuntimeError("code=103 permission denied"))
    avatars, clock = _avatars(tmp_path, adapter, "ann")
    assert await avatars.get("ch", "ann") is None
    assert await avatars.get("ch", "ann") is None
    assert adapter.asked == ["ann"]
    clock.now += RETRY_AFTER_SECONDS + 1
    assert await avatars.get("ch", "ann") is None
    assert adapter.asked == ["ann", "ann"]


async def test_no_picture_on_the_platform_drops_the_cached_one(tmp_path: Path) -> None:
    adapter = _Adapter(_PNG)
    avatars, clock = _avatars(tmp_path, adapter, "ann")
    assert await avatars.get("ch", "ann") is not None
    clock.now += REFRESH_AFTER_SECONDS + 1
    adapter.answer = None
    assert await avatars.get("ch", "ann") is None
    adapter.answer = _PNG
    # Not asked again within the hour; and the old picture is gone.
    assert await avatars.get("ch", "ann") is None


async def test_a_stale_picture_stands_when_the_refresh_fails(tmp_path: Path) -> None:
    adapter = _Adapter(_PNG)
    avatars, clock = _avatars(tmp_path, adapter, "ann")
    await avatars.get("ch", "ann")
    clock.now += REFRESH_AFTER_SECONDS + 1
    adapter.answer = RuntimeError("timeout")
    assert await avatars.get("ch", "ann") == Avatar(data=_PNG, content_type="image/png")


async def test_a_channel_not_running_here_serves_only_the_cache(tmp_path: Path) -> None:
    avatars, _ = _avatars(tmp_path, None, "ann")
    assert await avatars.get("ch", "ann") is None


async def test_not_an_image_is_no_picture(tmp_path: Path) -> None:
    avatars, _ = _avatars(tmp_path, _Adapter(b"<html>login</html>"), "ann")
    assert await avatars.get("ch", "ann") is None


async def test_only_a_paired_person_has_a_picture_and_removal_forgets_it(tmp_path: Path) -> None:
    adapter = _Adapter(_PNG)
    avatars, _ = _avatars(tmp_path, adapter, "ann")
    assert await avatars.get("ch", "bob") is None
    assert adapter.asked == []
    await avatars.get("ch", "ann")
    avatars.forget("ch", "ann")
    store = FileAvatarStore(tmp_path)
    assert store.read("ch", "ann") is None


def test_image_type_reads_the_bytes_not_a_declared_type() -> None:
    assert image_type(_PNG) == "image/png"
    assert image_type(_JPEG) == "image/jpeg"
    assert image_type(b"GIF89a....") == "image/gif"
    assert image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert image_type(b"<svg/>") is None
    assert image_type(b"") is None


def test_file_store_round_trips_and_forgets_a_channel(tmp_path: Path) -> None:
    store = FileAvatarStore(tmp_path)
    store.write("ch", "ann", Avatar(data=_PNG, content_type="image/png"))
    stored = store.read("ch", "ann")
    assert stored is not None and stored.avatar.data == _PNG
    # The sender id never names a path.
    assert all("ann" not in p.name for p in tmp_path.rglob("*"))
    store.forget("ch")
    assert store.read("ch", "ann") is None
