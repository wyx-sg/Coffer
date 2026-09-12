"""The tool surface the tidy pass hands its model.

Four operations over ONE collection — list, read, write, delete — and the
boundary that makes "stay inside this collection" a fact rather than an
instruction in a prompt. Every handler that can overwrite or retire a file
archives the prior revision first: the pass runs unattended with no review
step, so ``.history/`` is the entire safety net (spec knowledge FR-050).

Split out of ``tidy.py`` for the file-size ceiling; the pass itself owns when
the loop runs and what it reports.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.errors import KnowledgeError, KnowledgeFileNotFound
from coffer.infrastructure.knowledge import fs, paths

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TidyTool:
    """One tool as the agentic loop sees it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class Counters:
    """What the loop actually did, accumulated by the tool handlers."""

    def __init__(self) -> None:
        self.rewritten = 0
        self.merged = 0
        self.archived = 0


def file_count(collection: str) -> int:
    return fs.count_files(paths.collection_dir(collection))


def _same_collection(collection: str, relpath: str) -> bool:
    """Whether ``relpath`` names something inside ``collection``."""
    try:
        return paths.collection_of(relpath) == collection
    except KnowledgeError:
        return False


def _archive(relpath: str) -> bool:
    """Copy the current revision of ``relpath`` into ``.history/``.

    Returns whether anything was archived — a path that does not exist yet is a
    create, not an overwrite, and has no prior revision to keep.
    """
    try:
        fs.archive(relpath)
    except KnowledgeFileNotFound:
        return False
    return True


def build_tools(
    *,
    service: KnowledgeService,
    collection: str,
    actor: str,
    counters: Counters,
) -> list[TidyTool]:
    """The four file operations, fenced to one collection."""

    def _outside(relpath: str) -> dict[str, Any]:
        return {"error": f"{relpath!r} is outside the collection {collection!r}"}

    async def _list_files(args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("path") or collection).strip() or collection
        if not _same_collection(collection, target):
            return _outside(target)
        try:
            level = await service.list_level(target)
        except KnowledgeError as exc:
            return {"error": str(exc)}
        return {
            "path": level.path,
            "directories": [
                {"path": d.path, "file_count": d.file_count} for d in level.directories
            ],
            "files": [
                {"path": f.path, "title": f.title, "description": f.description}
                for f in level.files
            ],
        }

    async def _read_file(args: dict[str, Any]) -> dict[str, Any]:
        relpath = str(args.get("path") or "")
        if not _same_collection(collection, relpath):
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

    async def _write_file(args: dict[str, Any]) -> dict[str, Any]:
        relpath = str(args.get("path") or "").strip() or None
        directory = str(args.get("directory") or "").strip() or None
        target = relpath or directory
        if target is None:
            return {"error": "pass either 'path' (replace) or 'directory' (create)"}
        if not _same_collection(collection, target):
            return _outside(target)
        # The whole safety net, and it goes first: a replace that lands
        # before the archive would have destroyed the revision it replaces.
        if relpath is not None and await asyncio.to_thread(_archive, relpath):
            counters.archived += 1
        try:
            written = await service.write(
                title=str(args.get("title") or ""),
                description=str(args.get("description") or ""),
                body=str(args.get("body") or ""),
                directory=directory,
                relpath=relpath,
                actor=actor,
            )
        except KnowledgeError as exc:
            return {"error": str(exc)}
        counters.rewritten += 1
        return {"ok": True, "path": written.path}

    async def _delete_file(args: dict[str, Any]) -> dict[str, Any]:
        relpath = str(args.get("path") or "")
        if not _same_collection(collection, relpath):
            return _outside(relpath)
        if await asyncio.to_thread(_archive, relpath):
            counters.archived += 1
        try:
            await service.delete(relpath, actor=actor)
        except KnowledgeError as exc:
            return {"error": str(exc)}
        counters.merged += 1
        return {"ok": True, "path": relpath}

    path_property = {
        "type": "string",
        "description": f"Path relative to the knowledge root, inside {collection!r}.",
    }
    return [
        TidyTool(
            name="list_files",
            description=(
                "List one directory of the collection: its subdirectories, and "
                "its files with their title and description. Omit 'path' for "
                "the collection's own top level."
            ),
            input_schema={
                "type": "object",
                "properties": {"path": path_property},
            },
            handler=_list_files,
        ),
        TidyTool(
            name="read_file",
            description="Read one file in full — its title, description and whole body.",
            input_schema={
                "type": "object",
                "properties": {"path": path_property},
                "required": ["path"],
            },
            handler=_read_file,
        ),
        TidyTool(
            name="write_file",
            description=(
                "Create a file ('directory') or replace one in place ('path'). "
                "Exactly one of the two. The replaced revision is archived "
                "automatically."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Existing file to replace, in this collection.",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Folder to create a new file in, in this collection.",
                    },
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "One line saying what question this file answers.",
                    },
                    "body": {"type": "string", "description": "The Markdown content."},
                },
                "required": ["title", "description", "body"],
            },
            handler=_write_file,
        ),
        TidyTool(
            name="delete_file",
            description=(
                "Remove a file whose content now lives in another file. The "
                "removed revision is archived automatically."
            ),
            input_schema={
                "type": "object",
                "properties": {"path": path_property},
                "required": ["path"],
            },
            handler=_delete_file,
        ),
    ]
