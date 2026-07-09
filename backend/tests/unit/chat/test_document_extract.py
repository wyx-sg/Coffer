"""Document text-extraction seam tests (spec 009 FR-030).

A document attachment (PDF/office file) reaches the agent as extracted text
folded into the turn, not as a vision input or an opaque binary path. The engine
is behind the ``DocumentExtractor`` seam, so these tests use a fake — no
``markitdown`` install needed.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.attachment import Attachment
from coffer.infrastructure.chat import document_extract as doc_mod
from coffer.infrastructure.chat.document_extract import (
    default_document_extractor,
    extract_document_attachments,
    prompt_with_document_text,
)


class _FakeExtractor:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    async def extract(self, path: str) -> str:
        self.calls.append(path)
        return self.text


async def test_document_is_extracted_and_other_files_are_kept() -> None:
    extractor = _FakeExtractor("Quarterly revenue was $4.2M.")
    attachments = [
        Attachment(path="/tmp/report.pdf", mime="application/pdf", filename="report.pdf"),
        Attachment(path="/tmp/photo.png", mime="image/png", filename="photo.png"),
    ]

    kept, extracts = await extract_document_attachments(attachments, extractor)

    # The PDF became extracted text and is dropped from the attachments…
    assert extracts == [("report.pdf", "Quarterly revenue was $4.2M.")]
    assert extractor.calls == ["/tmp/report.pdf"]
    # …while the image is kept to be materialised as a vision block.
    assert [a.filename for a in kept] == ["photo.png"]


async def test_office_types_and_extension_fallback_are_documents() -> None:
    extractor = _FakeExtractor("slide text")
    attachments = [
        Attachment(
            path="/tmp/deck.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="deck.pptx",
        ),
        # A generic mime but a document filename → matched by extension.
        Attachment(path="/tmp/memo.docx", mime="application/octet-stream", filename="memo.docx"),
    ]

    kept, extracts = await extract_document_attachments(attachments, extractor)

    assert [name for name, _ in extracts] == ["deck.pptx", "memo.docx"]
    assert kept == []


async def test_audio_and_plain_text_are_not_documents() -> None:
    extractor = _FakeExtractor("should not be called")
    attachments = [
        Attachment(path="/tmp/voice.ogg", mime="audio/ogg", filename="voice.ogg"),
        Attachment(path="/tmp/notes.txt", mime="text/plain", filename="notes.txt"),
        Attachment(path="/tmp/main.py", mime="text/x-python", filename="main.py"),
    ]

    kept, extracts = await extract_document_attachments(attachments, extractor)

    # None are documents: audio is left for the transcriber, plain text/code is
    # read fine as a path by the agent.
    assert extracts == []
    assert extractor.calls == []
    assert [a.filename for a in kept] == ["voice.ogg", "notes.txt", "main.py"]


async def test_no_extractor_keeps_document_as_a_file() -> None:
    attachments = [
        Attachment(path="/tmp/report.pdf", mime="application/pdf", filename="report.pdf")
    ]

    kept, extracts = await extract_document_attachments(attachments, None)

    # Without an extractor the document is handed over as a file (path), unchanged
    # — the turn degrades, never wedges.
    assert extracts == []
    assert [a.filename for a in kept] == ["report.pdf"]


async def test_empty_extract_falls_back_to_the_document_file() -> None:
    extractor = _FakeExtractor("   ")  # extraction yielded nothing usable
    attachments = [
        Attachment(path="/tmp/report.pdf", mime="application/pdf", filename="report.pdf")
    ]

    kept, extracts = await extract_document_attachments(attachments, extractor)

    assert extracts == []
    assert [a.filename for a in kept] == ["report.pdf"]


def test_default_document_extractor_present_when_markitdown_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doc_mod.importlib.util, "find_spec", lambda name: object())
    assert default_document_extractor() is not None


def test_default_document_extractor_none_when_markitdown_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doc_mod.importlib.util, "find_spec", lambda name: None)
    assert default_document_extractor() is None


def test_prompt_with_document_text_folds_documents_into_the_text() -> None:
    assert prompt_with_document_text("hello", []) == "hello"
    folded = prompt_with_document_text("summarise this", [("report.pdf", "the body text")])
    assert folded.startswith("summarise this")
    assert "[Document: report.pdf]" in folded
    assert "the body text" in folded
    # With no caption, the extracted text is the whole prompt.
    assert prompt_with_document_text("", [("d.pdf", "body")]).startswith("[Document: d.pdf]")
