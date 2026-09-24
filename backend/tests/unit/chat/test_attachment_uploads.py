"""The web composer's upload rules and the service over them (spec chat "Upload
a file for a web message", "Send uploaded files with a web message").

Pure: the domain rules take bytes and names, and the service runs over the
in-memory ``FakeChatMediaStore`` — nothing touches the disk.
"""

from __future__ import annotations

import pytest

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.domain.chat.attachment import (
    GENERIC_MIME,
    INLINE_IMAGE_MAX_BYTES,
    MAX_ATTACHMENT_BYTES,
    Attachment,
    attachment_note,
    base64_size,
    clean_upload_filename,
    inline_image_mime,
    is_upload_id,
    sniff_image_mime,
    upload_mime,
)
from coffer.domain.chat.errors import (
    AttachmentNotFound,
    AttachmentTooLarge,
    AttachmentTypeUnsupported,
)

from .conftest import FakeChatMediaStore

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
_GIF = b"GIF89a\x01\x00"
_WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "

# ---------------------------------------------------------------------------
# upload_mime
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "declared", "data", "expected"),
    [
        # Declared image / audio / document types are taken as given.
        ("shot.png", "image/png", _PNG, "image/png"),
        ("voice.webm", "audio/webm", b"\x1a\x45\xdf\xa3", "audio/webm"),
        ("report.pdf", "application/pdf", b"%PDF-1.7\x00", "application/pdf"),
        # Parameters and case on the declared type are normalised away.
        ("a.jpg", "IMAGE/JPEG; charset=binary", _JPEG, "image/jpeg"),
        # A generic declared type falls back to the fixed extension table.
        (
            "deck.pptx",
            "application/octet-stream",
            b"PK\x03\x04\x00",
            ("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ),
        ("song.MP3", None, b"ID3\x00", "audio/mpeg"),
        # Text is recognised by its bytes, whatever the browser called it.
        ("main.ts", "video/mp2t", b"export const x = 1;\n", "text/plain"),
        ("notes.md", "text/markdown", b"# Title\n", "text/markdown"),
        ("README", "", "héllo wörld".encode(), "text/plain"),
    ],
)
def test_upload_mime_accepts_what_an_agent_can_use(
    filename: str, declared: str | None, data: bytes, expected: str
) -> None:
    assert upload_mime(filename, declared, data) == expected


@pytest.mark.parametrize(
    ("filename", "declared", "data"),
    [
        ("clip.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42"),
        ("bundle.zip", "application/zip", b"PK\x03\x04\x00\x00"),
        ("tool", "application/octet-stream", b"\xcf\xfa\xed\xfe\x00"),
        # Not UTF-8 and no accepted extension.
        ("latin1.txt.bak", None, b"caf\xe9"),
    ],
)
def test_upload_mime_refuses_other_binaries(
    filename: str, declared: str | None, data: bytes
) -> None:
    assert upload_mime(filename, declared, data) is None


@pytest.mark.parametrize(
    ("filename", "declared", "data", "expected"),
    [
        # The bytes decide an image's type, not the declared type or the name.
        ("photo.png", "image/png", _JPEG, "image/jpeg"),
        ("anim.webp", "image/webp", _GIF, "image/gif"),
        ("still.gif", "application/octet-stream", _WEBP, "image/webp"),
        ("scan.jpg", None, _PNG, "image/png"),
        # An image claim the bytes do not back is a generic file, never an image.
        ("fake.png", "image/png", b"not an image at all", GENERIC_MIME),
        ("photo.heic", "image/heic", b"\x00\x00\x00\x18ftypheic", GENERIC_MIME),
        ("logo.svg", None, b"<svg xmlns='http://www.w3.org/2000/svg'/>", GENERIC_MIME),
    ],
)
def test_upload_mime_stores_an_image_under_the_type_its_bytes_prove(
    filename: str, declared: str | None, data: bytes, expected: str
) -> None:
    assert upload_mime(filename, declared, data) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_PNG, "image/png"),
        (_JPEG, "image/jpeg"),
        (b"GIF87a\x01\x00", "image/gif"),
        (_GIF, "image/gif"),
        (_WEBP, "image/webp"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", None),  # a RIFF that is audio
        (b"\x89PNG", None),  # a truncated signature
        (b"", None),
    ],
)
def test_sniff_image_mime_recognises_the_four_inline_formats(
    data: bytes, expected: str | None
) -> None:
    assert sniff_image_mime(data) == expected


def test_base64_size_rounds_up_to_whole_quads() -> None:
    assert [base64_size(n) for n in (0, 1, 2, 3, 4)] == [0, 4, 4, 4, 8]


def test_inline_image_mime_admits_a_sniffed_image_up_to_the_encoded_ceiling() -> None:
    # 3/4 of the ceiling encodes to exactly the ceiling; one byte more is over.
    at_limit = INLINE_IMAGE_MAX_BYTES * 3 // 4
    assert base64_size(at_limit) == INLINE_IMAGE_MAX_BYTES
    assert inline_image_mime(_JPEG.ljust(at_limit, b"\x00")) == "image/jpeg"
    assert inline_image_mime(_JPEG.ljust(at_limit + 1, b"\x00")) is None


def test_inline_image_mime_refuses_bytes_that_are_not_an_inline_format() -> None:
    assert inline_image_mime(b"\x00\x00\x00\x18ftypheic") is None
    assert inline_image_mime(b"plain text") is None


def test_clean_upload_filename_keeps_the_last_segment_only() -> None:
    assert clean_upload_filename("../../etc/passwd") == "passwd"
    assert clean_upload_filename("C:\\Users\\me\\photo.png") == "photo.png"
    assert clean_upload_filename("bad\x00name\n.txt") == "badname.txt"
    assert clean_upload_filename("") == "attachment"
    assert clean_upload_filename(None) == "attachment"
    assert clean_upload_filename("dir/") == "attachment"
    assert len(clean_upload_filename("a" * 400 + ".txt")) == 255


def test_is_upload_id_accepts_only_32_hex() -> None:
    assert is_upload_id("0123456789abcdef0123456789abcdef")
    assert not is_upload_id("0123456789ABCDEF0123456789ABCDEF")
    assert not is_upload_id("../0123456789abcdef0123456789abcd")
    assert not is_upload_id("0123456789abcdef")


def test_attachment_note_names_the_files() -> None:
    img = Attachment(path="/x/a.png", mime="image/png", filename="a.png")
    pdf = Attachment(path="/x/b.pdf", mime="application/pdf", filename="b.pdf")
    assert attachment_note([img]) == "(sent 1 image: a.png)"
    assert attachment_note([img, pdf]) == "(sent 2 files: a.png, b.pdf)"


# ---------------------------------------------------------------------------
# ChatAttachmentService
# ---------------------------------------------------------------------------


async def test_upload_over_the_ceiling_is_refused_and_stores_nothing() -> None:
    store = FakeChatMediaStore()
    svc = ChatAttachmentService(store)
    with pytest.raises(AttachmentTooLarge) as exc:
        await svc.upload(
            filename="big.png", declared_mime="image/png", data=b"x" * (MAX_ATTACHMENT_BYTES + 1)
        )
    assert "20 MB" in str(exc.value)
    assert store.saved == {}


async def test_upload_of_an_unusable_type_is_refused_and_stores_nothing() -> None:
    store = FakeChatMediaStore()
    svc = ChatAttachmentService(store)
    with pytest.raises(AttachmentTypeUnsupported):
        await svc.upload(filename="clip.mp4", declared_mime="video/mp4", data=b"\x00\x01\x02")
    assert store.saved == {}


async def test_upload_stores_the_cleaned_name_and_resolved_type() -> None:
    store = FakeChatMediaStore()
    svc = ChatAttachmentService(store)
    stored = await svc.upload(
        filename="/tmp/secret/notes.md", declared_mime="text/markdown", data=b"# hi\n"
    )
    assert (stored.filename, stored.mime, stored.size) == ("notes.md", "text/markdown", 5)
    assert store.saved[stored.id][0] == b"# hi\n"


async def test_resolve_returns_attachments_in_send_order() -> None:
    svc = ChatAttachmentService(FakeChatMediaStore())
    first = await svc.upload(filename="a.png", declared_mime="image/png", data=b"a")
    second = await svc.upload(filename="b.txt", declared_mime="text/plain", data=b"b")
    resolved = await svc.resolve([second.id, first.id])
    assert [a.filename for a in resolved] == ["b.txt", "a.png"]
    assert await svc.resolve([]) == []


@pytest.mark.parametrize("bad_id", ["f" * 32, "../../etc/passwd", ""])
async def test_resolve_refuses_an_id_no_upload_stored(bad_id: str) -> None:
    svc = ChatAttachmentService(FakeChatMediaStore())
    with pytest.raises(AttachmentNotFound):
        await svc.resolve([bad_id])


def test_message_text_stands_in_only_for_an_attachment_only_message() -> None:
    img = Attachment(path="/x/a.png", mime="image/png", filename="a.png")
    assert ChatAttachmentService.message_text("look", [img]) == "look"
    assert ChatAttachmentService.message_text("  ", [img]) == "(sent 1 image: a.png)"
    assert ChatAttachmentService.message_text("plain", []) == "plain"


def test_title_hint_names_the_files_only_without_text() -> None:
    img = Attachment(path="/x/a.png", mime="image/png", filename="a.png")
    doc = Attachment(path="/x/b.pdf", mime="application/pdf", filename="b.pdf")
    assert ChatAttachmentService.title_hint("", [img, doc]) == "a.png, b.pdf"
    assert ChatAttachmentService.title_hint("hello", [img]) is None
    assert ChatAttachmentService.title_hint("", []) is None
