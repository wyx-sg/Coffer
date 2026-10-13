"""One Confluence page — its storage body, its attachments and what it is — as
a source: readable Markdown, the attachments it refers to and a report of
every part. The export itself is kept on this Mac as the upload's original,
like any other upload's (spec knowledge "Import a Confluence page as a readable
source with its attachments").

Two shapes of page export are read, both JSON, sniffed by content rather than
by name:

* the export a Confluence command-line tool writes for one page, ``"kind":
  "confluence.page"``, with ``pageId``, ``title``, ``version``, ``pageUrl``,
  ``spaceKey``, ``body`` in ``bodyFormat`` ``storage`` and ``attachments``,
  each carrying its file as ``dataBase64`` when it was downloaded;
* Confluence's own REST answer for a page (``GET /rest/api/content/{id}
  ?expand=body.storage,version,space``), which carries no attachments.

Coffer fetches nothing: whoever exports the page does so with their own access,
and what was not downloaded is reported missing, never fetched behind their back.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from coffer.domain.knowledge.converter import (
    BODY_CONVERTED,
    BODY_PARTIAL,
    ITEM_MISSING,
    ITEM_SKIPPED,
    Conversion,
    ImportItem,
    ImportReport,
)
from coffer.infrastructure.knowledge.converters.confluence import storage
from coffer.infrastructure.knowledge.converters.confluence.context import Context

CONVERTER = "confluence"
#: The frontmatter key a Confluence source records where it came from under.
ORIGIN_KEY = "origin"
SYSTEM = "confluence"


@dataclass(frozen=True)
class Page:
    """A page export, read."""

    page_id: str
    title: str
    version: int | None
    url: str
    space: str
    storage: str
    #: Attachment name → its bytes, for the ones that were downloaded.
    attachments: Mapping[str, bytes]
    #: Every attachment the export listed, downloaded or not.
    listed: tuple[str, ...]
    warnings: tuple[str, ...]


def _version(value: object) -> int | None:
    if isinstance(value, Mapping):
        value = value.get("number")
    if value is None or isinstance(value, bool) or not isinstance(value, int | str | float):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read(data: bytes) -> Page | None:
    """The page an export holds; ``None`` when ``data`` is not one."""
    if data.lstrip()[:1] != b"{":
        return None
    try:
        doc = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    if doc.get("kind") == "confluence.page":
        if str(doc.get("bodyFormat") or "storage") != "storage":
            return None
        files: dict[str, bytes] = {}
        listed: list[str] = []
        for item in doc.get("attachments") or []:
            if not isinstance(item, Mapping) or not item.get("name"):
                continue
            name = str(item["name"])
            listed.append(name)
            encoded = item.get("dataBase64")
            if isinstance(encoded, str):
                try:
                    files[name] = base64.b64decode(encoded, validate=False)
                except (binascii.Error, ValueError):
                    continue
        warnings = tuple(
            str(w.get("message") or w.get("code") or "")
            for w in doc.get("warnings") or []
            if isinstance(w, Mapping)
        )
        return Page(
            page_id=str(doc.get("pageId") or doc.get("id") or ""),
            title=str(doc.get("title") or ""),
            version=_version(doc.get("version")),
            url=str(doc.get("pageUrl") or doc.get("link") or ""),
            space=str(doc.get("spaceKey") or ""),
            storage=str(doc.get("body") or ""),
            attachments=files,
            listed=tuple(listed),
            warnings=tuple(w for w in warnings if w),
        )
    body = doc.get("body")
    stored = body.get("storage") if isinstance(body, Mapping) else None
    if doc.get("type") == "page" and isinstance(stored, Mapping) and "value" in stored:
        links_raw, space_raw = doc.get("_links"), doc.get("space")
        links = links_raw if isinstance(links_raw, Mapping) else {}
        space = space_raw if isinstance(space_raw, Mapping) else {}
        base, webui = str(links.get("base") or ""), str(links.get("webui") or "")
        return Page(
            page_id=str(doc.get("id") or ""),
            title=str(doc.get("title") or ""),
            version=_version(doc.get("version")),
            url=f"{base}{webui}" if webui else base,
            space=str(space.get("key") or ""),
            storage=str(stored.get("value") or ""),
            attachments={},
            listed=(),
            warnings=(),
        )
    return None


def folder_for(page: Page) -> str:
    """Where a page's files go: one folder per page and version, so a
    re-import of a newer version never overwrites what the older one kept."""
    version = f"-v{page.version}" if page.version is not None else ""
    return f"confluence-{page.page_id or 'page'}{version}"


def _companions(ctx: Context, page: Page) -> None:
    """Say which downloaded attachments nothing refers to."""
    for name in sorted(page.attachments):
        if any(i.name == name for i in ctx.attachment_items):
            continue
        ctx.attachment_items.append(ImportItem(name, ITEM_SKIPPED, "the page does not refer to it"))
    for name in page.listed:
        if not any(i.name == name for i in ctx.attachment_items):
            ctx.attachment_items.append(
                ImportItem(name, ITEM_SKIPPED, "the page does not refer to it")
            )


def convert(page: Page, *, fetched_at: str | None = None) -> Conversion:
    """The page as a source: its Markdown under its own title, its files, and
    the metadata and report its frontmatter keeps."""
    folder = folder_for(page)
    ctx = Context(folder=folder, attachments=dict(page.attachments))
    markdown = storage.convert(page.storage, ctx)
    _companions(ctx, page)
    title = page.title or f"Confluence page {page.page_id}"
    report = ImportReport(
        body=BODY_PARTIAL if ctx.partial else BODY_CONVERTED,
        attachments=tuple(ctx.attachment_items),
        macros=tuple(reversed(ctx.macro_items)),
        warnings=page.warnings,
    )
    origin: dict[str, Any] = {
        "system": SYSTEM,
        "url": page.url,
        "page_id": page.page_id,
        "space": page.space,
        "version": page.version,
        "fetched_at": fetched_at or datetime.now(UTC).replace(microsecond=0).isoformat(),
        "format": "confluence-storage",
    }
    return Conversion(
        markdown=f"# {title}\n\n{markdown}",
        title=title,
        converter=CONVERTER,
        metadata={ORIGIN_KEY: {k: v for k, v in origin.items() if v not in (None, "")}},
        files=tuple(ctx.files),
        asset_folder=folder,
        report=report,
    )


def missing(report: ImportReport) -> list[ImportItem]:
    return [i for i in (*report.attachments, *report.macros) if i.status == ITEM_MISSING]


__all__ = ["CONVERTER", "ORIGIN_KEY", "Page", "convert", "folder_for", "missing", "read"]
