"""The web composer's attachments (spec chat "Upload a file for a web message",
"Send uploaded files with a web message").

A channel downloads its media itself; the web page cannot hand the daemon a
file inside a JSON send, so it uploads each file first and sends the ids it got
back (ADR chat-attachment-uploads). This service owns both halves: the upload's
bounds (size, type) and the send-time resolution of ids into the ``Attachment``
references the turn orchestrator persists — exactly the references a channel
hands it, so every agent adapter materialises a web upload the way it already
materialises channel media.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.chat.ports import ChatMediaStore
from coffer.domain.chat.attachment import (
    MAX_ATTACHMENT_BYTES,
    Attachment,
    UploadedAttachment,
    attachment_note,
    clean_upload_filename,
    is_upload_id,
    upload_mime,
)
from coffer.domain.chat.errors import (
    AttachmentExpired,
    AttachmentNotFound,
    AttachmentTooLarge,
    AttachmentTypeUnsupported,
)
from coffer.domain.chat.message import AttachmentBlock, Message, TextBlock


class ChatAttachmentService:
    """Accept uploads within bounds; resolve their ids at send time."""

    def __init__(self, store: ChatMediaStore) -> None:
        self._store = store

    async def upload(
        self, *, filename: str | None, declared_mime: str | None, data: bytes
    ) -> UploadedAttachment:
        """Store one file. Raises ``AttachmentTooLarge`` over the ceiling and
        ``AttachmentTypeUnsupported`` for a type no agent can use; nothing is
        written in either case."""
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AttachmentTooLarge(len(data), MAX_ATTACHMENT_BYTES)
        name = clean_upload_filename(filename)
        mime = upload_mime(name, declared_mime, data)
        if mime is None:
            raise AttachmentTypeUnsupported(name, declared_mime)
        return await self._store.save(data=data, filename=name, mime=mime)

    async def resolve(self, attachment_ids: Sequence[str]) -> list[Attachment]:
        """The attachments a send names, in its order. Raises
        ``AttachmentNotFound`` for the first id that names no stored file, so a
        message is never sent missing a file its sender attached."""
        resolved: list[Attachment] = []
        for attachment_id in attachment_ids:
            found = (
                await self._store.resolve(attachment_id) if is_upload_id(attachment_id) else None
            )
            if found is None:
                raise AttachmentNotFound(attachment_id)
            resolved.append(found)
        return resolved

    async def reattach(self, message: Message) -> tuple[str, list[Attachment]]:
        """The text and files a persisted user message carries, to send it again
        (spec chat "Show a failed turn as one inline banner with Retry"). Raises
        ``AttachmentExpired`` for the first referenced file no longer on disk, so
        a retry never goes out without a file the original carried."""
        text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
        attachments = [
            Attachment(path=b.path, mime=b.mime, filename=b.filename)
            for b in message.content
            if isinstance(b, AttachmentBlock)
        ]
        for attachment in attachments:
            if not await self._store.present(attachment):
                raise AttachmentExpired(attachment.filename)
        return text, attachments

    @staticmethod
    def message_text(text: str, attachments: Sequence[Attachment]) -> str:
        """The text a send persists: its own, or — for a message that carries
        only files — the same short stand-in a channel's uncaptioned photo gets,
        because an agent's request cannot carry an empty text block."""
        if text.strip() or not attachments:
            return text
        return attachment_note(attachments)

    @staticmethod
    def title_hint(text: str, attachments: Sequence[Attachment]) -> str | None:
        """What a conversation opened by an attachment-only message is named
        after: its files' names, as a channel names one (spec chat "Persist
        conversations and messages in SQLite"). ``None`` when there is text."""
        if text.strip() or not attachments:
            return None
        return ", ".join(a.filename for a in attachments) or None


__all__ = ["ChatAttachmentService"]
