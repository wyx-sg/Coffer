"""Each paired person's picture on the platform, for the Channels page.

spec channels "Show each paired person's platform picture": the people list
shows the picture the person has on Telegram or SeaTalk, and their initials
when there is none. The picture is asked of the running adapter
(:class:`AvatarFetchPort`) the first time the page wants it, kept in a
machine-local cache (:class:`AvatarStorePort`, the ``derived`` class: deleting
it only costs a fetch), and asked again once a day so a changed picture shows.

Read on demand rather than at pairing: the same path then covers a person
paired before pictures existed, a pairing another machine made, and a picture
the person changed — and nothing is fetched for a channel nobody looks at.
Every failure reads as "no picture": the list falls back to initials, and a
refused or failed fetch is not retried for an hour, so a SeaTalk app without
the contacts permission is asked once an hour, not on every page load.

Application layer only; the files are infrastructure's, the HTTP calls the
adapters'.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from coffer.application.channel.people import people_of
from coffer.application.channel.store_ports import ChannelPeerRepoPort

__all__ = [
    "MAX_AVATAR_BYTES",
    "Avatar",
    "AvatarFetchPort",
    "AvatarStorePort",
    "PersonAvatars",
    "StoredAvatar",
    "image_type",
]

_logger = logging.getLogger(__name__)

#: A profile picture is a thumbnail; anything larger is not one.
MAX_AVATAR_BYTES = 2 * 1024 * 1024
#: How long a cached picture is shown before the platform is asked again.
REFRESH_AFTER_SECONDS = 24 * 3600.0
#: How long a failed or empty answer stands before the platform is asked again.
RETRY_AFTER_SECONDS = 3600.0
#: The page waits this long for a picture before it settles for initials.
FETCH_TIMEOUT_SECONDS = 8.0

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def image_type(data: bytes) -> str | None:
    """The image type ``data`` is, read from its first bytes; ``None`` when it
    is not one of the types a profile picture comes in (or is too large). The
    declared content type is never trusted: the bytes are served back as this
    type."""
    if not data or len(data) > MAX_AVATAR_BYTES:
        return None
    for magic, mime in _SIGNATURES:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class Avatar:
    """A picture, as bytes and the image type they were read as."""

    data: bytes
    content_type: str


@dataclass(frozen=True)
class StoredAvatar:
    """A cached picture and when it was fetched (epoch seconds)."""

    avatar: Avatar
    fetched_at: float


@runtime_checkable
class AvatarFetchPort(Protocol):
    """An adapter that can read a person's picture off its platform."""

    async def fetch_avatar(self, sender_id: str) -> bytes | None:
        """The picture's bytes; ``None`` when the person has none. Raises when
        the platform could not be asked or refused (a missing permission)."""
        ...


class AvatarStorePort(Protocol):
    """The machine-local cache of pictures, one per channel and person."""

    def read(self, channel_uid: str, sender_id: str) -> StoredAvatar | None: ...

    def write(self, channel_uid: str, sender_id: str, avatar: Avatar) -> None: ...

    def forget(self, channel_uid: str, sender_id: str | None = None) -> None:
        """Drop one person's picture, or every picture of the channel."""
        ...


class PersonAvatars:
    """Answers "what is this person's picture?" for the Channels page."""

    def __init__(
        self,
        *,
        store: AvatarStorePort,
        peers: ChannelPeerRepoPort,
        adapter_of: Callable[[str], object | None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._peers = peers
        self._adapter_of = adapter_of
        self._clock = clock
        #: ``(channel uid, sender id) -> when the platform last had nothing``.
        self._missed: dict[tuple[str, str], float] = {}

    async def get(self, channel_uid: str, sender_id: str) -> Avatar | None:
        """The person's picture, or ``None`` (show initials). Only a person
        paired to the channel has one here: a removed person's cached picture
        is dropped the next time it is asked for."""
        if not any(
            p.sender_id == sender_id
            for p in people_of(await self._peers.list_by_resource(channel_uid))
        ):
            self._store.forget(channel_uid, sender_id)
            return None
        now = self._clock()
        cached = self._store.read(channel_uid, sender_id)
        if cached is not None and now - cached.fetched_at < REFRESH_AFTER_SECONDS:
            return cached.avatar
        stale = cached.avatar if cached is not None else None
        missed = self._missed.get((channel_uid, sender_id))
        if missed is not None and now - missed < RETRY_AFTER_SECONDS:
            return stale
        adapter = self._adapter_of(channel_uid)
        if not isinstance(adapter, AvatarFetchPort):
            # Not running on this machine (or a transport with no pictures):
            # whatever was cached is still the best answer.
            return stale
        try:
            data = await asyncio.wait_for(adapter.fetch_avatar(sender_id), FETCH_TIMEOUT_SECONDS)
        except Exception as exc:  # any failure is "no new picture"
            _logger.info(
                "channel.avatar.fetch_failed",
                extra={"channel": channel_uid, "error": type(exc).__name__},
            )
            self._missed[(channel_uid, sender_id)] = now
            return stale
        content_type = image_type(data) if data else None
        if data is None or content_type is None:
            # The person has no picture (or one we will not serve): drop the old one.
            self._missed[(channel_uid, sender_id)] = now
            self._store.forget(channel_uid, sender_id)
            return None
        avatar = Avatar(data=data, content_type=content_type)
        self._missed.pop((channel_uid, sender_id), None)
        self._store.write(channel_uid, sender_id, avatar)
        return avatar

    def forget(self, channel_uid: str, sender_id: str | None = None) -> None:
        """Drop a removed person's picture, or a deleted channel's."""
        self._store.forget(channel_uid, sender_id)
        for key in [k for k in self._missed if k[0] == channel_uid]:
            if sender_id is None or key[1] == sender_id:
                del self._missed[key]
