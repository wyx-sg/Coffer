"""What a person uploads for a Confluence page, read into one :class:`StorageInput`.

Accepted by content (design §5): a page read result in JSON — the Confluence
REST content shape or a CLI read result — or a Storage Format file. Anything
else answers ``None`` so the registry falls back (a non-Confluence ``.json``
stays passthrough).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import pathlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: Elements only Confluence Storage Format carries.
_STORAGE_SIGNS = re.compile(r"<(?:ac|ri):[a-z]")
_STORAGE_SUFFIX = ".storage.xml"


@dataclass(frozen=True)
class StorageInput:
    """One Confluence page as uploaded: its Storage XML and what is known of it.

    ``body_format`` is ``"storage"``, or ``"markdown"`` for a CLI read result
    whose body is Markdown with storage markers (section 6).
    """

    title: str
    body: str
    body_format: str = "storage"
    page_id: str = ""
    version: int | None = None
    space: str = ""
    origin: str = ""
    retrieved_at: str = ""
    redaction: str = ""
    #: Attachment bytes by the attachment's original name.
    attachments: Mapping[str, bytes] = field(default_factory=dict, hash=False)
    #: Attachments the export names without their bytes.
    listed: frozenset[str] = frozenset()
    #: The original upload's bytes, for a folder name when there is no id.
    digest: str = ""


def _text(value: object) -> str:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return str(value).strip()
    return ""


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if isinstance(value, dict):
        return _int(value.get("number"))
    return None


def _redaction(doc: Mapping[str, Any]) -> str:
    value = doc.get("redaction", doc.get("redacted"))
    if isinstance(value, bool):
        return "redacted" if value else "none"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) or "none"
    return _text(value) or "none"


def _attachments(items: object) -> tuple[dict[str, bytes], frozenset[str]]:
    found: dict[str, bytes] = {}
    listed: set[str] = set()
    if not isinstance(items, list):
        return found, frozenset()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name") or item.get("title"))
        if not name:
            continue
        encoded = item.get("dataBase64")
        if isinstance(encoded, str) and encoded:
            try:
                found[name] = base64.b64decode(encoded, validate=False)
                continue
            except (binascii.Error, ValueError):
                pass
        listed.add(name)
    return found, frozenset(listed - set(found))


def _from_rest(doc: Mapping[str, Any], digest: str) -> StorageInput | None:
    body = doc.get("body")
    storage = body.get("storage") if isinstance(body, dict) else None
    value = storage.get("value") if isinstance(storage, dict) else None
    if not isinstance(value, str):
        return None
    links = doc.get("_links") if isinstance(doc.get("_links"), dict) else {}
    origin = _text(links.get("base")) + _text(links.get("webui")) if links else ""
    space = doc.get("space")
    return StorageInput(
        title=_text(doc.get("title")),
        body=value,
        page_id=_text(doc.get("id")),
        version=_int(doc.get("version")),
        space=_text(space.get("key")) if isinstance(space, dict) else "",
        origin=origin,
        retrieved_at=_text(doc.get("retrievedAt") or doc.get("retrieved_at")),
        redaction=_redaction(doc),
        digest=digest,
    )


def _from_cli(doc: Mapping[str, Any], digest: str) -> StorageInput | None:
    body = doc.get("body")
    body_format = _text(doc.get("bodyFormat")).lower()
    is_page = doc.get("kind") == "confluence.page" or bool(doc.get("pageId"))
    if not isinstance(body, str) or not is_page or body_format not in ("storage", "markdown"):
        return None
    attachments, listed = _attachments(doc.get("attachments"))
    return StorageInput(
        title=_text(doc.get("title")),
        body=body,
        body_format=body_format,
        page_id=_text(doc.get("pageId") or doc.get("id")),
        version=_int(doc.get("version")),
        space=_text(doc.get("spaceKey") or doc.get("space")),
        origin=_text(doc.get("pageUrl") or doc.get("link")),
        retrieved_at=_text(doc.get("retrievedAt") or doc.get("retrieved_at")),
        redaction=_redaction(doc),
        attachments=attachments,
        listed=listed,
        digest=digest,
    )


def _title_from(filename: str) -> str:
    name = pathlib.Path(filename).name
    if name.lower().endswith(_STORAGE_SUFFIX):
        return name[: -len(_STORAGE_SUFFIX)]
    return pathlib.Path(name).stem


def parse_export(data: bytes, filename: str) -> StorageInput | None:
    """The Confluence page ``data`` holds, or ``None`` when it is not one."""
    suffix = pathlib.Path(filename).suffix.lower()
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if suffix == ".json":
        try:
            doc = json.loads(text)
        except ValueError:
            return None
        if not isinstance(doc, dict):
            return None
        return _from_cli(doc, digest) or _from_rest(doc, digest)
    if suffix == ".xml":
        named = filename.lower().endswith(_STORAGE_SUFFIX)
        if not (named or _STORAGE_SIGNS.search(text)):
            return None
        if text.lstrip().startswith("<?xml") and not _STORAGE_SIGNS.search(text):
            return None
        return StorageInput(title=_title_from(filename), body=text, digest=digest)
    return None
