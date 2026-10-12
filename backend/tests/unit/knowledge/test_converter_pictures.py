"""Taking the pictures out of an uploaded document (ADR
knowledge-sources-keep-their-images-and-originals-stay-on-this-mac; spec
knowledge "Keep the pictures of an upload beside its source")."""

from __future__ import annotations

import base64
import io
import pathlib

import pytest
from PIL import Image

from coffer.infrastructure.knowledge.converters.images import (
    MAX_IMAGES,
    Pictures,
    pdf_pictures,
    take_data_uris,
    with_pdf_pictures,
)


def _image(color: str = "red", side: int = 64, fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (side, side), color).save(buffer, format=fmt)
    return buffer.getvalue()


def _uri(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a document's pictures are taken out, decorations and repeats dropped",
)
def test_inlined_pictures_become_named_files_once_each() -> None:
    logo, chart, bullet = _image("red"), _image("green"), _image("blue", side=12)
    markdown = (
        f"![logo]({_uri(logo)})\n\n![Chart]({_uri(chart)})\n\n"
        f"![]({_uri(bullet)})\n\n![logo again]({_uri(logo)})\n"
    )
    pictures = Pictures()

    out = take_data_uris(markdown, pictures)

    assert [p.name for p in pictures.kept] == ["image-1.png", "image-2.png"]
    assert out.splitlines()[0] == "![logo](image-1.png)"
    assert "![Chart](image-2.png)" in out
    # The 12-pixel bullet is a decoration: dropped, with nothing left of it.
    assert "data:" not in out
    assert "![logo again](image-1.png)" in out


def test_a_format_a_browser_cannot_show_is_kept_as_png() -> None:
    pictures = Pictures()
    name = pictures.add(_image(fmt="TIFF"))
    assert name == "image-1.png"
    assert Image.open(io.BytesIO(pictures.kept[0].data)).format == "PNG"


def test_a_jpeg_keeps_its_format_and_unreadable_bytes_are_dropped() -> None:
    pictures = Pictures()
    assert pictures.add(_image(fmt="JPEG")) == "image-1.jpg"
    assert pictures.add(b"not a picture") is None
    assert (
        take_data_uris("![x](data:image/png;base64,@@@)", pictures)
        == "![x](data:image/png;base64,@@@)"
    )


def test_no_upload_keeps_more_than_the_limit() -> None:
    pictures = Pictures()
    for n in range(MAX_IMAGES + 5):
        pictures.add(_image(color=(n, n, n), side=50))  # type: ignore[arg-type]
    assert len(pictures.kept) == MAX_IMAGES


def test_a_pdfs_pictures_are_listed_under_the_page_they_came_from(tmp_path: pathlib.Path) -> None:
    pdf = tmp_path / "deck.pdf"
    pages = [Image.new("RGB", (200, 200), c) for c in ("red", "green")]
    pages[0].save(pdf, format="PDF", save_all=True, append_images=pages[1:])
    pictures = Pictures()

    placed = pdf_pictures(pdf, pictures)

    assert [page for page, _ in placed] == [1, 2]
    out = with_pdf_pictures("Some text.", placed)
    assert out.startswith("Some text.\n\n## Images")
    assert f"Page 2:\n\n![Page 2]({placed[1][1]})" in out
    assert with_pdf_pictures("Some text.", []) == "Some text."


def test_an_unreadable_pdf_yields_no_pictures(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7 broken")
    assert pdf_pictures(bad, Pictures()) == []
