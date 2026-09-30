"""The documents Coffer parses in the vault, as JSON (spec vault-storage).

A vault document is a JSON object: 2-space indent, keys in the order the file
already had them, a trailing newline. Two rules make it safe for several builds
and a person to share:

- **Unknown fields are kept.** A reader validates the fields it knows and
  carries every other key verbatim, in place; a write puts them back where they
  were. They are reported as warnings, never refused.
- **The encoding is deterministic.** The same document always encodes to the
  same bytes, so a write that changes nothing makes no commit and two machines
  writing the same value do not conflict.

A **resource document** (``resources/<kind>/<name>.json``) holds what the
resource *is* — ``uid``, ``kind``, ``format_version``, ``name``, an optional
``title``, ``description``, ``config``, ``created_at`` — and nothing about
where it reaches: ``enabled`` and ``scope`` are machine-local and live in
``local/`` (ADR reach-is-a-machine-local-predicate-over-a-context). There is
no ``updated_at``: two machines stamping it would conflict on every edit, and
git already knows when a file changed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from coffer.domain.vault.formats import FORMAT_COMPAT_KEY, FORMAT_VERSION_KEY

#: The resource document's own fields, in the order a new file is written.
RESOURCE_FIELDS = (
    "uid",
    "kind",
    FORMAT_VERSION_KEY,
    FORMAT_COMPAT_KEY,
    "name",
    "title",
    "description",
    "config",
    "created_at",
)
_REQUIRED = ("kind", "name", "config")


class DocumentInvalid(ValueError):  # noqa: N818
    """The bytes are not the document their path says they are."""


def decode(data: bytes) -> dict[str, Any]:
    """Parse a vault document; the top level must be an object."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DocumentInvalid(f"not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DocumentInvalid("a vault document must be a JSON object")
    return value


def encode(doc: Mapping[str, Any]) -> bytes:
    """The one encoding of a vault document."""
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def merge_ordered(
    original: Mapping[str, Any] | None,
    known: Mapping[str, Any],
    canonical: tuple[str, ...],
) -> dict[str, Any]:
    """``known`` written over ``original``, keeping ``original``'s key order and
    every key it had that ``known`` does not name.

    A known key whose value is ``None`` and that ``original`` did not have is
    left out, so an optional field is not written as ``null`` by default. A
    known key new to the file is placed after the last canonical key before it
    that the file already has.
    """
    out: dict[str, Any] = {}
    base = dict(original or {})
    for key, value in base.items():
        if key in known:
            if known[key] is None and key not in _KEEP_NULL:
                continue
            out[key] = known[key]
        else:
            out[key] = value
    for key in canonical:
        if key in known and key not in out and (known[key] is not None or key in _KEEP_NULL):
            out = _insert_after(out, key, known[key], canonical)
    for key, value in known.items():
        if key not in out and key not in canonical and value is not None:
            out[key] = value
    return out


#: Optional fields a resource document writes even when empty, so a person
#: editing the file sees where they go.
_KEEP_NULL = frozenset({"description"})


def _insert_after(
    doc: dict[str, Any], key: str, value: Any, canonical: tuple[str, ...]
) -> dict[str, Any]:
    before = canonical[: canonical.index(key)]
    anchor = next((k for k in reversed(before) if k in doc), None)
    if anchor is None:
        return {key: value, **doc}
    out: dict[str, Any] = {}
    for k, v in doc.items():
        out[k] = v
        if k == anchor:
            out[key] = value
    return out


@dataclass(frozen=True)
class ResourceDocument:
    """A resource file, as read. ``uid`` is ``None`` for a hand-made file that
    has not been given one yet; ``raw`` is the whole object as it was on disk,
    unknown fields included, so a write can put them back."""

    kind: str
    name: str
    config: dict[str, Any]
    uid: str | None = None
    description: str | None = None
    title: str | None = None
    created_at: str | None = None
    format_version: int = 1
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        return tuple(k for k in self.raw if k not in RESOURCE_FIELDS)

    def replace(self, **changes: Any) -> ResourceDocument:
        return replace(self, **changes)

    def to_bytes(self, *, format_version: int | None = None) -> bytes:
        known: dict[str, Any] = {
            "uid": self.uid,
            "kind": self.kind,
            FORMAT_VERSION_KEY: format_version or self.format_version,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "config": self.config,
            "created_at": self.created_at,
        }
        return encode(merge_ordered(self.raw, known, RESOURCE_FIELDS))


def parse_resource(data: bytes) -> ResourceDocument:
    """Read a resource document; raise ``DocumentInvalid`` for anything that
    is not one. Unknown fields are kept in ``raw``, never refused."""
    raw = decode(data)
    for key in _REQUIRED:
        if key not in raw:
            raise DocumentInvalid(f"missing field: {key}")
    kind, name, config = raw["kind"], raw["name"], raw["config"]
    if not isinstance(kind, str) or not kind:
        raise DocumentInvalid("kind must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise DocumentInvalid("name must be a non-empty string")
    if not isinstance(config, dict):
        raise DocumentInvalid("config must be an object")
    uid = raw.get("uid")
    if uid is not None and (not isinstance(uid, str) or not _is_uid(uid)):
        raise DocumentInvalid("uid must be an opaque id (letters, digits, - and _), or absent")
    for key in ("description", "title", "created_at"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            raise DocumentInvalid(f"{key} must be a string or null")
    version = raw.get(FORMAT_VERSION_KEY, 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise DocumentInvalid(f"{FORMAT_VERSION_KEY} must be a positive integer")
    return ResourceDocument(
        kind=kind,
        name=name,
        config=config,
        uid=uid,
        description=raw.get("description"),
        title=raw.get("title"),
        created_at=raw.get("created_at"),
        format_version=version,
        raw=raw,
    )


_UID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _is_uid(value: str) -> bool:
    """Minted uids are ``uuid4().hex``; any opaque id of this shape is kept."""
    return bool(_UID.match(value))


__all__ = [
    "RESOURCE_FIELDS",
    "DocumentInvalid",
    "ResourceDocument",
    "decode",
    "encode",
    "merge_ordered",
    "parse_resource",
]
