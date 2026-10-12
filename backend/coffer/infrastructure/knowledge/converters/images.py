"""The pictures in an uploaded document, taken out so its source keeps them
(ADR knowledge-sources-keep-their-images-and-originals-stay-on-this-mac; spec
knowledge "Keep the pictures of an upload beside its source").

MarkItDown can inline the pictures of an Office or HTML document as ``data:``
URIs (``keep_data_uris``); :func:`take_data_uris` turns each into a named
picture the Markdown links to. A PDF's text layer carries no pictures, so
:func:`pdf_pictures` reads them from the PDF itself, page by page, and
:func:`with_pdf_pictures` lists them after the text under the page they came
from.

What is kept is bounded: decorations (rules, bullets, icons — anything under
:data:`MIN_SIDE` pixels on a side) are dropped, a picture
over :data:`MAX_IMAGE_BYTES` is dropped, a repeat of one already kept (a logo
on every slide) is kept once, and no upload keeps more than :data:`MAX_IMAGES`.
A picture in a format a browser cannot show is re-encoded as PNG.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import logging
import pathlib
import re
import tempfile

from coffer.domain.knowledge.converter import ConvertedImage

logger = logging.getLogger(__name__)

MIN_SIDE = 48
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 40

#: Formats kept as they are, by Pillow's name for them, with their extension.
_WEB_FORMATS = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}

_DATA_URI = re.compile(
    r"!\[(?P<alt>[^\]\n]*)\]\(data:image/[A-Za-z0-9.+-]+;base64,(?P<data>[A-Za-z0-9+/=\s]+)\)"
)


def _web_image(data: bytes) -> tuple[bytes, str] | None:
    """``data`` as a picture a browser shows, with its extension; ``None`` for a
    decoration, an unreadable picture or one too large to keep."""
    from PIL import Image  # lazy: only an upload with pictures pays for it

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if min(image.size) < MIN_SIDE:
                return None
            ext = _WEB_FORMATS.get(image.format or "")
            if ext is None:
                buffer = io.BytesIO()
                converted = image if image.mode in ("RGB", "RGBA", "L") else image.convert("RGBA")
                converted.save(buffer, format="PNG")
                data, ext = buffer.getvalue(), "png"
    except Exception:
        return None
    return (data, ext) if len(data) <= MAX_IMAGE_BYTES else None


class Pictures:
    """The pictures one upload keeps, named ``image-1.png``, ``image-2.jpg`` …"""

    def __init__(self) -> None:
        self.kept: list[ConvertedImage] = []
        self._by_digest: dict[str, str] = {}

    def add(self, data: bytes) -> str | None:
        """Keep ``data`` and return its name, the earlier name of the same
        picture, or ``None`` when it is not kept."""
        digest = hashlib.sha256(data).hexdigest()
        if digest in self._by_digest:
            return self._by_digest[digest]
        if len(self.kept) >= MAX_IMAGES:
            return None
        web = _web_image(data)
        if web is None:
            return None
        body, ext = web
        name = f"image-{len(self.kept) + 1}.{ext}"
        self.kept.append(ConvertedImage(name=name, data=body))
        self._by_digest[digest] = name
        return name


def take_data_uris(markdown: str, pictures: Pictures) -> str:
    """``markdown`` with each inlined ``data:`` picture kept and linked by name,
    or dropped (its alt text left, when it has one)."""

    def _swap(match: re.Match[str]) -> str:
        alt = match.group("alt").strip()
        try:
            data = base64.b64decode("".join(match.group("data").split()), validate=True)
        except (binascii.Error, ValueError):
            return alt
        name = pictures.add(data)
        return f"![{alt}]({name})" if name else alt

    return _DATA_URI.sub(_swap, markdown)


def pdf_pictures(path: pathlib.Path, pictures: Pictures) -> list[tuple[int, str]]:
    """The pictures of the PDF at ``path`` worth keeping, as (page number, name)
    in page order; a PDF pdfminer cannot read yields none."""
    from pdfminer.high_level import extract_pages
    from pdfminer.image import ImageWriter
    from pdfminer.layout import LTFigure, LTImage

    def _images(item: object) -> list[LTImage]:
        if isinstance(item, LTImage):
            return [item]
        if isinstance(item, LTFigure):
            return [found for child in item for found in _images(child)]
        return []

    placed: list[tuple[int, str]] = []
    try:
        with tempfile.TemporaryDirectory() as out:
            writer = ImageWriter(out)
            for number, page in enumerate(extract_pages(str(path)), start=1):
                for image in (found for item in page for found in _images(item)):
                    if len(pictures.kept) >= MAX_IMAGES:
                        return placed
                    try:
                        written = pathlib.Path(out) / writer.export_image(image)
                        name = pictures.add(written.read_bytes())
                    except Exception:
                        continue
                    if name and (number, name) not in placed:
                        placed.append((number, name))
    except Exception:
        logger.info("knowledge.pdf_pictures.unreadable", exc_info=True)
    return placed


def with_pdf_pictures(markdown: str, placed: list[tuple[int, str]]) -> str:
    """``markdown`` followed by the PDF's pictures, each under its page."""
    if not placed:
        return markdown
    lines = [markdown.rstrip(), "", "## Images", ""]
    for number, name in placed:
        lines += [f"Page {number}:", "", f"![Page {number}]({name})", ""]
    return "\n".join(lines)


__all__ = [
    "MAX_IMAGES",
    "MAX_IMAGE_BYTES",
    "MIN_SIDE",
    "Pictures",
    "pdf_pictures",
    "take_data_uris",
    "with_pdf_pictures",
]
