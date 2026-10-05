"""Where the command-line tools a person added by hand are kept.

The declarations are a vault state document, ``state/cli-tools/tools.json`` —
machine-independent, so they travel with the vault. The same document keeps,
under ``notes``, the description a person wrote for a tool they did not add (one
a skill or MCP server requires). Where a tool was found on
this machine (when it was added by an absolute path) is machine-local state
under ``local/`` and never synced.
"""

from __future__ import annotations

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

    def save(self, tools: list[DeclaredTool], *, summary: str, actor: str | None = None) -> None:
        self._write(tools, self.notes(), summary=summary, actor=actor)

    def set_note(
        self, command: str, text: str | None, *, summary: str, actor: str | None = None
    ) -> None:
        """Keep ``text`` as ``command``'s description; ``None`` drops it."""
        notes = self.notes()
        if text is None:
            notes.pop(command, None)
        else:
            notes[command] = text
        self._write(self.all(), notes, summary=summary, actor=actor)

    def _write(
        self,
        tools: list[DeclaredTool],
        notes: dict[str, str],
        *,
        summary: str,
        actor: str | None,
    ) -> None:
        if not tools and not notes:
            self._doc.remove(summary=summary, actor=actor)
            return
        body: dict[str, Any] = {"tools": [to_document(t) for t in sorted_tools(tools)]}
        if notes:
            body["notes"] = dict(sorted(notes.items()))
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
