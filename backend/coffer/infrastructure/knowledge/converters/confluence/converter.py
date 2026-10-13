"""The Confluence converter: an export the person fetched → a readable source.

:func:`convert_export` turns one :class:`StorageInput` into a
:class:`Conversion`: the Markdown body, the files kept beside it (pictures the
body shows, diagram sources, ``page.storage.xml`` as it came), what could not
be kept, and the frontmatter keys of design §5. :class:`ConfluenceConverter`
is the registry's entry: it claims an upload by content (:meth:`sniff`), never
by extension alone.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Callable
from datetime import UTC, datetime

from coffer.domain.knowledge.converter import Conversion, ConversionIssue, UnsupportedDocument
from coffer.infrastructure.knowledge.converters.confluence.export import (
    StorageInput,
    parse_export,
)
from coffer.infrastructure.knowledge.converters.confluence.kept import (
    NOT_RENDERED,
    Kept,
    asset_link,
    safe_name,
)
from coffer.infrastructure.knowledge.converters.confluence.markers import (
    expand_storage_markers,
)
from coffer.infrastructure.knowledge.converters.confluence.storage import Walker

CONVERTER_NAME = "confluence"
STORAGE_FILE = "page.storage.xml"
REPRESENTATION = "markdown from confluence storage"
MARKDOWN_REPRESENTATION = "markdown from a confluence markdown export"
_SNIFFED = (".json", ".xml")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60].rstrip("-") or "confluence-page"


def asset_folder(inp: StorageInput) -> str:
    """``confluence-<pageId>-v<version>``, or ``<title-slug>-<sha8>`` with no id."""
    if inp.page_id:
        base = f"confluence-{safe_name(inp.page_id)}"
        return f"{base}-v{inp.version}" if inp.version is not None else base
    return f"{_slug(inp.title)}-{inp.digest[:8]}" if inp.digest else _slug(inp.title)


def import_status(issues: tuple[ConversionIssue, ...]) -> str:
    """``partial`` whenever an issue other than ``not_rendered`` exists."""
    return "partial" if any(i.kind != NOT_RENDERED for i in issues) else "complete"


def _metadata(
    inp: StorageInput,
    *,
    now: datetime,
    issues: tuple[ConversionIssue, ...],
    records: list[dict[str, object]],
    from_storage: bool,
) -> dict[str, object]:
    meta: dict[str, object] = {}
    if inp.origin:
        meta["origin"] = inp.origin
    if inp.page_id:
        meta["page_id"] = inp.page_id
    if inp.version is not None:
        meta["page_version"] = inp.version
    if inp.space:
        meta["space"] = inp.space
    meta["retrieved_at"] = inp.retrieved_at or now.isoformat(timespec="seconds")
    if from_storage:
        meta["representation"] = REPRESENTATION
        meta["original_representation"] = asset_link(STORAGE_FILE)
    else:
        meta["representation"] = MARKDOWN_REPRESENTATION
    meta["redaction"] = inp.redaction or "none"
    meta["attachments"] = records
    meta["import_status"] = import_status(issues)
    meta["import_issues"] = [{"kind": i.kind, "name": i.name, "reason": i.reason} for i in issues]
    return meta


def convert_export(inp: StorageInput, *, now: datetime) -> Conversion:
    """The readable source for one Confluence page export."""
    title = inp.title or (f"Confluence page {inp.page_id}" if inp.page_id else "Confluence page")
    if inp.body_format == "markdown":
        markdown, issues = expand_storage_markers(inp.body)
        return Conversion(
            markdown=markdown,
            title=title,
            converter=CONVERTER_NAME,
            issues=issues,
            metadata=_metadata(inp, now=now, issues=issues, records=[], from_storage=False),
            asset_folder="",
            keeps_original=True,
        )
    kept = Kept(
        attachments=inp.attachments,
        listed=inp.listed,
        keep_files=True,
        page_title=inp.title,
    )
    kept.keep(STORAGE_FILE, inp.body.encode("utf-8"))
    markdown = Walker(kept).markdown(inp.body)
    issues = tuple(kept.issues)
    return Conversion(
        markdown=markdown,
        title=title,
        converter=CONVERTER_NAME,
        files=tuple(kept.files),
        issues=issues,
        metadata=_metadata(
            inp, now=now, issues=issues, records=list(kept.records.values()), from_storage=True
        ),
        asset_folder=asset_folder(inp),
        keeps_original=True,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ConfluenceConverter:
    """Implements ``Converter`` for Confluence page exports, claimed by content."""

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def can_handle(self, fmt: str) -> bool:
        """Never by extension alone: the registry asks :meth:`sniff` first."""
        return False

    def sniff(self, data: bytes, filename: str) -> bool:
        """Whether ``data`` is a Confluence page export this converter reads."""
        if pathlib.Path(filename).suffix.lower() not in _SNIFFED:
            return False
        return parse_export(data, filename) is not None

    async def convert(self, data: bytes, filename: str) -> Conversion:
        inp = parse_export(data, filename)
        if inp is None:
            raise UnsupportedDocument(pathlib.Path(filename).suffix.lstrip(".").lower())
        return convert_export(inp, now=self._clock())
