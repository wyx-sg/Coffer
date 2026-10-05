"""The machine-local cache of paired people's pictures (``AvatarStorePort``).

``~/.coffer/derived/channel-avatars/<channel uid>/<sha256 of sender id>``: the
``derived`` class (ADR storage-is-five-classes-by-nature), because every file
is a copy of what the platform holds and deleting it only costs a fetch. One
file per person holding the image bytes alone; its type is read back from the
bytes and its age from the file's modification time, so there is no index to
drift from the files. The sender id is hashed into the name so a platform id
can never name a path.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from coffer.application.channel.avatars import Avatar, StoredAvatar, image_type
from coffer.infrastructure.vault.home import derived_root

__all__ = ["AVATAR_DIR_NAME", "FileAvatarStore"]

#: The directory's name under ``derived/``.
AVATAR_DIR_NAME = "channel-avatars"


class FileAvatarStore:
    """One image file per channel and person, under ``root``."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def _base(self) -> Path:
        # Resolved at every call, so a test that repoints HOME moves it too.
        return self._root if self._root is not None else derived_root() / AVATAR_DIR_NAME

    def _channel_dir(self, channel_uid: str) -> Path:
        return self._base() / hashlib.sha256(channel_uid.encode()).hexdigest()[:32]

    def _path(self, channel_uid: str, sender_id: str) -> Path:
        return self._channel_dir(channel_uid) / hashlib.sha256(sender_id.encode()).hexdigest()[:32]

    def read(self, channel_uid: str, sender_id: str) -> StoredAvatar | None:
        path = self._path(channel_uid, sender_id)
        try:
            data = path.read_bytes()
            fetched_at = path.stat().st_mtime
        except OSError:
            return None
        content_type = image_type(data)
        if content_type is None:
            return None
        return StoredAvatar(Avatar(data=data, content_type=content_type), fetched_at=fetched_at)

    def write(self, channel_uid: str, sender_id: str, avatar: Avatar) -> None:
        path = self._path(channel_uid, sender_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written beside and renamed over, so a reader never sees half a picture.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".avatar-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(avatar.data)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def forget(self, channel_uid: str, sender_id: str | None = None) -> None:
        if sender_id is None:
            shutil.rmtree(self._channel_dir(channel_uid), ignore_errors=True)
            return
        with contextlib.suppress(OSError):
            self._path(channel_uid, sender_id).unlink()
