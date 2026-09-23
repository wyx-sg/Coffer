"""The tool surface a curation pass hands its model.

Four operations over ONE collection's documents — list, read, write, retire —
and the boundaries that make the pass's rules facts rather than requests in a
prompt (spec knowledge FR-021):

* **One collection, documents only.** No handler can name a path in another
  collection, the collection's ``README.md``, or the hidden inbox the material
  came from.
* **Eight writes, then the pass stops** (FR-025). One piece of material must
  never be able to trigger a corpus-wide rewrite, however sure the model is.
* **A document may not name another file** (FR-027). Checked at the write,
  because asking for it in a prompt is what produced 343 dead references.

Split out of ``curate.py`` for the file-size ceiling; the pass itself owns when
the loop runs and what it reports.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.errors import KnowledgeError
from coffer.infrastructure.knowledge import catalogue, fs, paths

logger = logging.getLogger(__name__)

#: Writes one pass may make (FR-025).
MAX_WRITES_PER_PASS = 8

#: Anything that looks like it names a Markdown file. Only the ones that turn
#: out to name a file in *this* corpus are refused — a document about a
#: repository may legitimately mention that repository's own `AGENTS.md`, and
#: refusing that would be a rule the model cannot satisfy.
_MD_TOKEN = re.compile(r"[\w一-鿿][\w一-鿿.\-/]*\.md\b")


@dataclass(frozen=True)
class CurationTool:
    """One tool as the agentic loop sees it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class Counters:
    """What the loop actually did, accumulated by the tool handlers."""

    def __init__(self) -> None:
        self.written = 0
        self.retired = 0
        self.refused = 0

    @property
    def writes(self) -> int:
        """Writes against the bound — a retire is a write of the corpus too."""
        return self.written + self.retired


def document_count(collection: str) -> int:
    return catalogue.count_files(paths.collection_dir(collection), markdown_only=True)


def offending_reference(body: str, known_names: frozenset[str], *, collection: str) -> str | None:
    """The first reference to a knowledge file in ``body``, if any (FR-027).

    ``known_names`` is the set of file names the collection actually holds, so
    the check is "does this name one of ours" rather than "does this contain a
    dot-md" — the second would forbid a document from mentioning a repository's
    own files, which is often the useful thing to say.

    A path into this collection is refused whatever it names, because that is
    this corpus by construction. It is anchored on the collection, not matched
    as a substring: a repository with a ``docs/shopee/overview.md`` in it is a
    perfectly good thing for a document to mention, and refusing that would be
    a rule the model cannot satisfy.
    """
    prefix = f"{collection}/"
    for match in _MD_TOKEN.finditer(body):
        token = match.group(0)
        if token.startswith(prefix):
            return token
        if token.rsplit("/", 1)[-1] in known_names:
            return token
    return None


def build_tools(
    *,
    service: KnowledgeService,
    collection: str,
    actor: str,
    counters: Counters,
) -> list[CurationTool]:
    """The four operations, fenced to one collection's documents."""

    def _document_path(relpath: str) -> str | None:
        """``relpath`` if it names a document in this collection."""
        try:
            if paths.collection_of(relpath) != collection:
                return None
            paths.require_document(relpath)
        except KnowledgeError:
            return None
        return relpath

    def _outside(relpath: str) -> dict[str, Any]:
        counters.refused += 1
        return {
            "error": (
                f"{relpath!r} is not a document of {collection!r}. "
                f"This pass may only read and write documents under {collection}/."
            )
        }

    def _folder(raw: str) -> list[str]:
        """``folder`` as segments inside the collection, however it was spelled.

        A model shown paths like ``demo/x.md`` naturally answers with
        ``folder="demo"``, and appending that to the collection would produce
        ``demo/demo/x.md`` — a trap found by running a real pass. Rather than
        refuse a reasonable spelling, strip the prefix that is this layer's to
        add.
        """
        segments = [s for s in raw.strip("/").split("/") if s]
        if segments and segments[0] == collection:
            segments = segments[1:]
        return segments

    def _known_names() -> frozenset[str]:
        return frozenset(
            entry.path.rsplit("/", 1)[-1]
            for entry in catalogue.walk_files(paths.collection_dir(collection))
        )

    async def _list_documents(_args: dict[str, Any]) -> dict[str, Any]:
        entries = catalogue.walk_files(paths.collection_dir(collection))
        return {
            "documents": [
                {"path": e.path, "title": e.title, "description": e.description} for e in entries
            ]
        }

    async def _read_document(args: dict[str, Any]) -> dict[str, Any]:
        relpath = str(args.get("path") or "")
        if _document_path(relpath) is None:
            return _outside(relpath)
        try:
            found = await service.read(relpath)
        except KnowledgeError as exc:
            return {"error": str(exc)}
        return {
            "path": found.path,
            "title": found.title,
            "description": found.description,
            "body": found.body,
        }

    async def _write_document(args: dict[str, Any]) -> dict[str, Any]:
        if counters.writes >= MAX_WRITES_PER_PASS:
            return {
                "error": (
                    f"this pass has already written {MAX_WRITES_PER_PASS} files, which is "
                    "its limit. Stop now; the next pass continues from here."
                )
            }
        relpath = str(args.get("path") or "").strip() or None
        folder = str(args.get("folder") or "").strip()
        if relpath is not None and _document_path(relpath) is None:
            return _outside(relpath)
        body = str(args.get("body") or "")
        offender = offending_reference(body, _known_names(), collection=collection)
        if offender is not None:
            counters.refused += 1
            return {
                "error": (
                    f"this body references the file {offender!r}. Document paths move as the "
                    "corpus is reorganised, so name the subject in prose instead of the file."
                )
            }
        try:
            written = fs.write_file(
                directory="/".join([collection, *_folder(folder)]),
                title=str(args.get("title") or ""),
                description=str(args.get("description") or ""),
                body=body,
                actor=actor,
                relpath=relpath,
                curated=True,
            )
        except KnowledgeError as exc:
            return {"error": str(exc)}
        counters.written += 1
        return {
            "ok": True,
            "path": written.path,
            "writes_left": MAX_WRITES_PER_PASS - counters.writes,
        }

    async def _retire_document(args: dict[str, Any]) -> dict[str, Any]:
        if counters.writes >= MAX_WRITES_PER_PASS:
            return {"error": f"this pass has already written {MAX_WRITES_PER_PASS} files."}
        relpath = str(args.get("path") or "")
        if _document_path(relpath) is None:
            return _outside(relpath)
        try:
            fs.delete_file(relpath)
        except KnowledgeError as exc:
            return {"error": str(exc)}
        counters.retired += 1
        return {"ok": True, "path": relpath}

    path_property = {
        "type": "string",
        "description": f"A document's path, e.g. '{collection}/example.md'.",
    }
    return [
        CurationTool(
            name="list_documents",
            description=(
                "Every document in this collection, with its title and "
                "one-line description. Use it to find the right home for new "
                "material before assuming there is none."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_list_documents,
        ),
        CurationTool(
            name="read_document",
            description=(
                "Read one document in full. Never rewrite a document you "
                "have not read: you are integrating into it, not replacing it."
            ),
            input_schema={
                "type": "object",
                "properties": {"path": path_property},
                "required": ["path"],
            },
            handler=_read_document,
        ),
        CurationTool(
            name="write_document",
            description=(
                "Write a document: pass 'path' to replace an existing one "
                "in place, or omit it (with an optional 'folder') to create a "
                "new one named after its title. The description is what a "
                "future reader chooses by, so make it say what question the "
                "document answers. Do not name other files in the body."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Existing document to replace, in this collection.",
                    },
                    "folder": {
                        "type": "string",
                        "description": (
                            "Optional subfolder for a new document, relative to "
                            "the collection — just the folder name, not a path "
                            "that repeats the collection."
                        ),
                    },
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "One line saying what question this document answers.",
                    },
                    "body": {"type": "string", "description": "The Markdown content."},
                },
                "required": ["title", "description", "body"],
            },
            handler=_write_document,
        ),
        CurationTool(
            name="retire_document",
            description=(
                "Remove a document whose content you have already written "
                "into another document in this same pass. Never use it to drop "
                "material: nothing here is archived."
            ),
            input_schema={
                "type": "object",
                "properties": {"path": path_property},
                "required": ["path"],
            },
            handler=_retire_document,
        ),
    ]
