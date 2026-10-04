"""Where the command-line tools a person added by hand are kept.

The declarations are a vault state document, ``state/cli-tools/tools.json`` —
machine-independent, so they travel with the vault. Where a tool was found on
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

    def save(self, tools: list[DeclaredTool], *, summary: str, actor: str | None = None) -> None:
        if not tools:
            self._doc.remove(summary=summary, actor=actor)
            return
        body: dict[str, Any] = {"tools": [to_document(t) for t in sorted_tools(tools)]}
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
