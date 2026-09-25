"""File-backed store for the web composer's uploads (spec chat "Upload a file
for a web message"; ADR chat-attachment-uploads).

Each upload is two flat files under ``~/.coffer/chat-media``: the bytes, named
``<id><ext>`` so an agent handed the path still sees the file's extension, and
``<id>.json`` recording the display name, type, size and the bytes' file name.
Flat on purpose: the retention sweep (``coffer.infrastructure.media_retention``)
ages files out one by one, exactly as it does ``channel-media``. The id is 32
hex characters from ``uuid4``; nothing a client sends is ever joined into a
path except an id already checked to have that shape.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import re
import uuid
from datetime import datetime

from coffer.domain.chat.attachment import Attachment, UploadedAttachment, is_upload_id
from coffer.domain.retention import MEDIA_RETENTION_DAYS
from coffer.infrastructure.media_retention import prune_media_dir

_logger = logging.getLogger(__name__)

#: An extension worth keeping on the stored bytes: short and plain.
_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,10}$")


def default_chat_media_dir() -> pathlib.Path:
    """``~/.coffer/chat-media`` — beside ``channel-media``. ``HOME`` is honoured
    (not ``Path.home()``) so tests redirect it to a tmp dir, the same way the
    channel media dir is resolved."""
    home = pathlib.Path(os.environ.get("HOME") or "~").expanduser()
    return home / ".coffer" / "chat-media"


class FileChatMediaStore:
    """``ChatMediaStore`` over a directory of flat files."""

    def __init__(self, root: pathlib.Path) -> None:
        self._root = root

    @property
    def root(self) -> pathlib.Path:
        return self._root

    async def save(self, *, data: bytes, filename: str, mime: str) -> UploadedAttachment:
        return await asyncio.to_thread(self._save, data, filename, mime)

    async def resolve(self, attachment_id: str) -> Attachment | None:
        return await asyncio.to_thread(self._resolve, attachment_id)

    async def present(self, attachment: Attachment) -> bool:
        return await asyncio.to_thread(pathlib.Path(attachment.path).is_file)

    def prune(self, now: datetime) -> list[str]:
        """Delete stored files older than the media retention window — the
        sweep the composition root binds into the retention cadence."""
        return prune_media_dir(self._root, max_age_days=MEDIA_RETENTION_DAYS, now=now)

    # -- blocking halves, run off the event loop ----------------------------

    def _save(self, data: bytes, filename: str, mime: str) -> UploadedAttachment:
        self._root.mkdir(parents=True, exist_ok=True)
        attachment_id = uuid.uuid4().hex
        suffix = pathlib.PurePath(filename).suffix.lower()
        stored = f"{attachment_id}{suffix if _SAFE_SUFFIX.fullmatch(suffix) else ''}"
        (self._root / stored).write_bytes(data)
        meta = {"filename": filename, "mime": mime, "size": len(data), "stored": stored}
        # The record is written last: an id resolves only once its bytes exist.
        (self._root / f"{attachment_id}.json").write_text(json.dumps(meta), encoding="utf-8")
        _logger.info("chat.media.saved id=%s mime=%s size=%d", attachment_id, mime, len(data))
        return UploadedAttachment(id=attachment_id, filename=filename, mime=mime, size=len(data))

    def _resolve(self, attachment_id: str) -> Attachment | None:
        if not is_upload_id(attachment_id):
            return None
        try:
            meta = json.loads((self._root / f"{attachment_id}.json").read_text(encoding="utf-8"))
            stored = str(meta["stored"])
            filename = str(meta["filename"])
            mime = str(meta["mime"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        # ``stored`` came from this store, but it is read back from disk: it must
        # still be this id's own file and nothing else.
        if not stored.startswith(attachment_id) or "/" in stored or "\\" in stored:
            return None
        path = self._root / stored
        if not path.is_file():
            return None
        return Attachment(path=str(path), mime=mime, filename=filename)


__all__ = ["FileChatMediaStore", "default_chat_media_dir"]
