"""Where the command-line tools a person added by hand are kept.

The declarations are a vault state document, ``state/cli-tools/tools.json`` —
machine-independent, so they travel with the vault. The same document keeps
what a person changed on a tool they did not add (one a skill or MCP server
requires): its description under ``notes``, and its display name, minimum
version and login check under ``edits``, one entry per command shaped like a
declaration without a description. Where a tool was found on
this machine (when it was added by an absolute path) is machine-local state
under ``local/`` and never synced.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from coffer.domain.skill.cli_declared import DeclaredTool, from_document, to_document
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.state_documents import StateDocument

AREA = "cli-tools"
DOC = "tools"


class VaultCliToolRepo:
    """``DeclaredToolsPort`` over ``state/cli-tools/tools.json``."""

    def __init__(self, *, home: Path | None = None) -> None:
        self._doc = StateDocument(AREA, DOC, home=home)

    def all(self) -> list[DeclaredTool]:
        doc = self._doc.get() or {}
        tools = (from_document(entry) for entry in doc.get("tools", []))
        return sorted((t for t in tools if t is not None), key=lambda t: t.command)

    def notes(self) -> dict[str, str]:
        """The descriptions written for tools nobody added by hand, by command."""
        raw = (self._doc.get() or {}).get("notes")
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and v}

    def edits(self) -> dict[str, DeclaredTool]:
        """The display name, minimum and login check changed on tools nobody
        added by hand, by command."""
        raw = (self._doc.get() or {}).get("edits", [])
        found = (from_document(entry) for entry in raw if isinstance(raw, list))
        return {t.command: replace(t, description=None) for t in found if t is not None}

    def save(self, tools: list[DeclaredTool], *, summary: str, actor: str | None = None) -> None:
        # A tool now added by hand carries its own fields; its edits go.
        edits = {k: v for k, v in self.edits().items() if all(t.command != k for t in tools)}
        self._write(tools, self.notes(), edits, summary=summary, actor=actor)

    def set_edit(
        self,
        command: str,
        edit: DeclaredTool | None,
        note: str | None,
        *,
        summary: str,
        actor: str | None = None,
    ) -> None:
        """Keep ``note`` as ``command``'s description and ``edit``'s display
        name, minimum and login check; ``None`` drops either."""
        notes, edits = self.notes(), self.edits()
        if note is None:
            notes.pop(command, None)
        else:
            notes[command] = note
        if edit is None:
            edits.pop(command, None)
        else:
            edits[command] = replace(edit, description=None)
        self._write(self.all(), notes, edits, summary=summary, actor=actor)

    def _write(
        self,
        tools: list[DeclaredTool],
        notes: dict[str, str],
        edits: dict[str, DeclaredTool],
        *,
        summary: str,
        actor: str | None,
    ) -> None:
        if not tools and not notes and not edits:
            self._doc.remove(summary=summary, actor=actor)
            return
        body: dict[str, Any] = {"tools": [to_document(t) for t in sorted_tools(tools)]}
        if notes:
            body["notes"] = dict(sorted(notes.items()))
        if edits:
            body["edits"] = [to_document(t) for t in sorted_tools(list(edits.values()))]
        self._doc.put(body, summary=summary, actor=actor)


def sorted_tools(tools: list[DeclaredTool]) -> list[DeclaredTool]:
    return sorted(tools, key=lambda t: t.command)


class LocalCliPaths:
    """``CliPathsPort``: the absolute path a tool was added by, on this machine."""

    def __init__(self, *, home: Path | None = None) -> None:
        self._store = JsonStore(lambda: local_root(home) / "cli-paths.json")

    def get(self, command: str) -> str | None:
        value = self._store.read().get(command)
        return value if isinstance(value, str) else None

    def set(self, command: str, path: str) -> None:
        self._store.update(lambda d: d.__setitem__(command, path))

    def drop(self, command: str) -> None:

        def forget(doc: dict[str, Any]) -> None:
            doc.pop(command, None)

        self._store.update(forget)


__all__ = ["LocalCliPaths", "VaultCliToolRepo"]
