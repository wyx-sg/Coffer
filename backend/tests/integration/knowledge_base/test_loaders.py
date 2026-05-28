"""Tests for the loaders module (text extraction whitelist).

PDF tests (TEST22-017) cover both the happy path (a tiny in-repo PDF
fixture with embedded text — keeps `_read_pdf` honest at ~100% coverage)
and the missing-engine path (pypdf monkey-removed → ``EngineUnavailable``).
"""

from __future__ import annotations

import builtins
import io

import pytest

from coffer.domain.errors import EngineUnavailable, IngestRejected
from coffer.infrastructure.knowledge_base import loaders as kb_loaders
from coffer.infrastructure.knowledge_base.loaders import (
    SUPPORTED_EXTENSIONS,
    extract_text,
)


async def test_markdown_extraction(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# hello\n\nworld")
    text = await extract_text(p, ".md")
    assert "hello" in text
    assert "world" in text


async def test_unsupported_extension(tmp_path):
    p = tmp_path / "a.xyz"
    p.write_bytes(b"\x00\x01\x02")
    with pytest.raises(IngestRejected) as exc:
        await extract_text(p, ".xyz")
    assert exc.value.reason == "unsupported_type"


def test_whitelist_includes_common_extensions():
    for ext in (".md", ".txt", ".py", ".ts", ".pdf", ".yaml"):
        assert ext in SUPPORTED_EXTENSIONS


# --------------------------------------------------------------------------- #
# TEST22-017 — _read_pdf coverage
# --------------------------------------------------------------------------- #


def _build_tiny_text_pdf() -> bytes:
    """Construct a ~1 KB PDF with a single page that contains the literal
    string "Hello PDF Coffer". Built at test time (no binary fixture in git)
    using ``pypdf``'s primitives so the dependency stays pinned in one place.
    """
    from pypdf import PdfWriter
    from pypdf.generic import (
        DictionaryObject,
        NameObject,
        NumberObject,
        StreamObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    content_bytes = b"BT /F1 12 Tf 50 100 Td (Hello PDF Coffer) Tj ET"
    stream = StreamObject()
    stream._data = content_bytes  # pypdf's only path here
    stream[NameObject("/Length")] = NumberObject(len(content_bytes))

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)

    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    content_ref = writer._add_object(stream)

    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = content_ref

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def test_pdf_extraction_happy_path(tmp_path):
    """A minimal PDF with embedded text must extract that text."""
    pdf_bytes = _build_tiny_text_pdf()
    # Sanity: shape and header.
    assert pdf_bytes.startswith(b"%PDF-"), pdf_bytes[:8]
    assert 100 < len(pdf_bytes) < 5_000  # ~700 bytes in practice

    p = tmp_path / "doc.pdf"
    p.write_bytes(pdf_bytes)

    text = await extract_text(p, ".pdf")
    assert "Hello PDF Coffer" in text


async def test_pdf_extraction_raises_engine_unavailable_without_pypdf(tmp_path, monkeypatch):
    """If ``pypdf`` is not importable, ``extract_text`` must surface
    ``EngineUnavailable("pypdf", …)`` so the HTTP surface can map it to
    503 ``ENGINE_UNAVAILABLE``."""
    # Drop the already-imported pypdf modules so the ``import pypdf`` inside
    # ``_read_pdf`` actually re-runs and hits the failing import hook.
    import sys

    real_import = builtins.__import__
    monkeypatch.setitem(sys.modules, "pypdf", None)  # forces ImportError on lookup

    def _no_pypdf(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pypdf" or name.startswith("pypdf."):
            raise ImportError(f"simulated missing pypdf for {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _no_pypdf)

    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n%minimal-no-real-content\n")

    with pytest.raises(EngineUnavailable) as exc:
        await extract_text(p, ".pdf")
    assert exc.value.engine == "pypdf"
    assert exc.value.code == "ENGINE_UNAVAILABLE"


def test_loaders_module_exports():
    """Pin the module's public-ish symbols so import paths in code/tests
    don't silently regress (the loaders module is referenced by the
    composition root)."""
    assert callable(kb_loaders.extract_text)
    assert ".pdf" in kb_loaders.PDF_EXTENSIONS
    assert ".md" in kb_loaders.TEXT_EXTENSIONS
    # Sanity: PDF + text + nothing else.
    assert kb_loaders.SUPPORTED_EXTENSIONS == kb_loaders.TEXT_EXTENSIONS | kb_loaders.PDF_EXTENSIONS
