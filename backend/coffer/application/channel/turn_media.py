"""The reply-file sentinel: how an agent hands the user a real file.

Split out of ``turn_render`` (behaviour-preserving) so the renderer module
holds only the turn-event → chat-traffic path. The agent opts in by writing a
line-anchored ``MEDIA:/absolute/path`` (optionally ``| caption``); ordinary
prose — including a legitimate markdown image the agent wrote only to
*reference* a file — never uploads anything.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.reply_shape import ReplyFile
from coffer.domain.channel.envelopes import SentMessage
from coffer.domain.chat.attachment import Attachment

#: Told about each uploaded file's message, so the reply it belongs to can be withdrawn.
OnFileSent = Callable[[SentMessage], None]

#: A line-anchored ``MEDIA:/abs/path`` sentinel, with an optional ``| caption``
#: after a pipe. Unlike markdown image syntax this never collides with prose.
#: The path group allows spaces (absolute macOS paths routinely contain them).
_MEDIA_MARKER = re.compile(
    r"^[ \t]*MEDIA:[ \t]*(?P<path>[^|\n]*?)[ \t]*(?:\|[ \t]*(?P<caption>[^\n]*?))?[ \t]*$",
    re.MULTILINE,
)
_MEDIA_MAX_BYTES = 50 * 1024 * 1024  # Telegram sendDocument caps at 50 MB
_PHOTO_MAX_BYTES = 10 * 1024 * 1024  # sendPhoto caps at 10 MB — larger images go as documents
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


def conversation_title_hint(text: str, attachments: Sequence[Attachment]) -> str:
    """What a conversation opened by this message should be named after (spec chat
    "Keep the conversation index without its text").

    Take it from the message the person sent — its own text, its own files —
    and take it BEFORE any context block (the origin header, fetched thread
    history) is folded into the turn text: those blocks are identical on every
    turn of every chat, and naming from them gave the chat list a column of
    indistinguishable conversations.

    With no words at all (a photo or a file on its own) the filenames stand in,
    rather than ``attachment_note``'s sentence: they are the one part of such a
    message a human recognises in a list, and they do not spend the title's
    first characters on wording every image-only conversation would share —
    which is the very failure this rule exists to fix. Nothing nameable ⇒ ``""``,
    and the conversation honestly keeps its placeholder title.
    """
    return text.strip() or ", ".join(a.filename for a in attachments if a.filename)


def _is_image_path(path: str) -> bool:
    return pathlib.Path(path).suffix.lower() in _IMAGE_SUFFIXES


def _deliverable(path: str) -> bool:
    """A marker is honoured only for an absolute path to a real, sane-sized file —
    so a relative path or a bare mention in prose never uploads by accident."""
    if not os.path.isabs(path):
        return False
    try:
        p = pathlib.Path(path)
        return bool(p.is_file() and p.stat().st_size <= _MEDIA_MAX_BYTES)
    except OSError:
        return False


@dataclass(frozen=True)
class MediaFile:
    """A file an agent's ``MEDIA:`` line hands the user, with the line's caption."""

    path: str
    caption: str = ""

    @property
    def name(self) -> str:
        return pathlib.Path(self.path).name


def take_media(adapter: ChannelAdapter, text: str) -> tuple[str, tuple[MediaFile, ...]]:
    """Take each ``MEDIA:`` sentinel line whose file exists out of ``text``;
    return the text without those lines and the files to upload after the reply.

    The files are uploaded only once the reply has gone out (``send_media_files``),
    so the reply leads and its files follow it. On a channel without file
    support the line is replaced with a plain note instead, so the user never
    sees a raw local path for a file that was never delivered.
    """
    supports = adapter.capabilities.supports_media
    files: list[MediaFile] = []
    out = text
    for match in _MEDIA_MARKER.finditer(text):
        path = (match.group("path") or "").strip()
        caption = (match.group("caption") or "").strip()
        if not _deliverable(path):
            continue  # not a real absolute file — leave the line untouched
        if not supports:
            label = caption or pathlib.Path(path).name
            out = out.replace(
                match.group(0),
                f"(couldn't send '{label}' — this channel has no file support)",
                1,
            ).strip()
            continue
        files.append(MediaFile(path=path, caption=caption))
        out = out.replace(match.group(0), "", 1).strip()
    return out, tuple(files)


def attachment_lines(files: Sequence[MediaFile]) -> str:
    """``📎 report.csv — what it is``, one line per file: where a file message
    cannot carry its own caption, the reply names its files instead of a text
    message following each one."""
    return "\n".join(f"📎 {f.name} — {f.caption}" if f.caption else f"📎 {f.name}" for f in files)


async def send_media_files(
    adapter: ChannelAdapter,
    chat_id: str,
    files: Sequence[MediaFile],
    *,
    thread_id: str = "",
    chat_kind: str = "direct",
    on_sent: OnFileSent | None = None,
) -> tuple[MediaFile, ...]:
    """Upload the files ``take_media`` took, after the reply. A caption rides on
    the file only where the transport's file messages carry one; elsewhere the
    reply already named it. Return the files that failed to upload."""
    caps = adapter.capabilities
    failed: list[MediaFile] = []
    for file in files:
        try:
            # sendPhoto caps at 10 MB; a larger image goes as a document.
            as_photo = (
                _is_image_path(file.path)
                and pathlib.Path(file.path).stat().st_size <= _PHOTO_MAX_BYTES
            )
            if caps.supports_typing:
                # An upload of any size shows a busy signal; saying WHAT it is
                # busy with beats claiming to type while a file goes up.
                with contextlib.suppress(Exception):
                    await adapter.send_typing(
                        chat_id,
                        thread_id=thread_id,
                        chat_kind=chat_kind,
                        action="upload_photo" if as_photo else "upload_document",
                    )
            sent_file = await adapter.send_media(
                chat_id,
                file.path,
                caption=(file.caption or None) if caps.media_captions else None,
                as_photo=as_photo,
                thread_id=thread_id,
                chat_kind=chat_kind,
            )
            if on_sent is not None:
                on_sent(sent_file)
        except Exception:
            failed.append(file)
    return tuple(failed)


async def send_reply_files(
    adapter: ChannelAdapter,
    chat_id: str,
    files: Sequence[ReplyFile],
    *,
    thread_id: str = "",
    chat_kind: str = "direct",
    on_sent: OnFileSent | None = None,
) -> int:
    """Upload the files a shaped reply carries beside its text (a table's CSV,
    a long log — see "Shape a reply for what the chat can show"), after the
    text that points at them. Each is written to a fresh temporary directory
    under its own name, so the chat shows ``table-1.csv`` rather than a random
    one. Best-effort: a file that fails is skipped, the reply already landed. The
    directory is removed once the uploads are done."""
    if not files or not adapter.capabilities.supports_media:
        return 0
    sent = 0
    with tempfile.TemporaryDirectory(prefix="coffer-reply-") as staged:
        for file in files:
            path = pathlib.Path(staged) / file.filename
            try:
                path.write_text(file.content, encoding="utf-8")
                sent_file = await adapter.send_media(
                    chat_id, str(path), as_photo=False, thread_id=thread_id, chat_kind=chat_kind
                )
                if on_sent is not None:
                    on_sent(sent_file)
            except Exception:
                continue
            sent += 1
    return sent
