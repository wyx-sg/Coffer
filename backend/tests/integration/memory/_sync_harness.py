"""A memory sync over real git checkouts, real agent directories and a real
vault, for the sync's acceptance tests.

One vault (the test's ``HOME``) can stand for the hub two machines share: a
:class:`Machine` is a machine id, its own agent config directories and its own
ledger file, so two of them over one vault are two machines after a vault
sync round, without running one.
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.sync_service import MemorySyncService
from coffer.application.memory.sync_view import MemorySyncView
from coffer.infrastructure.memory.readers import MEMORY_READERS
from coffer.infrastructure.memory.sync_ledger import LedgerStore, PreviewStore
from coffer.infrastructure.memory.writers import MEMORY_WRITERS
from coffer.infrastructure.secret.detector import detect
from tests.unit.memory.conftest import FakeAudit


def cc_file(name: str, description: str, type_: str, body: str) -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  type: {type_}\n---\n\n{body}\n"
    )


def cc_slug(root: pathlib.Path) -> str:
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in str(root))


def cc_memory_dir(config_dir: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    return config_dir / "projects" / cc_slug(root) / "memory"


def cc_project(config_dir: pathlib.Path, root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A Claude Code project directory for ``root`` holding ``files``."""
    memory = cc_memory_dir(config_dir, root)
    memory.mkdir(parents=True, exist_ok=True)
    (memory.parent / "session.jsonl").write_text(
        json.dumps({"type": "user", "cwd": str(root)}) + "\n", encoding="utf-8"
    )
    for name, text in files.items():
        (memory / name).write_text(text, encoding="utf-8")
    return memory


def codex_memory(groups: Sequence[tuple[str, str, Sequence[str]]]) -> str:
    """A Codex ``MEMORY.md``: ``(title, cwd, reusable-knowledge bullets)``."""
    parts = []
    for title, cwd, bullets in groups:
        lines = [f"# Task Group: {title}", f"applies_to: cwd={cwd}", "", "## Reusable knowledge"]
        lines += [f"- {b}" for b in bullets]
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def codex_dir(
    config_dir: pathlib.Path,
    memory_md: str = "",
    summary_md: str = "",
    *,
    memories_on: bool = True,
) -> pathlib.Path:
    memories = config_dir / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "MEMORY.md").write_text(memory_md, encoding="utf-8")
    if summary_md:
        (memories / "memory_summary.md").write_text(summary_md, encoding="utf-8")
    flag = "true" if memories_on else "false"
    (config_dir / "config.toml").write_text(f"[features]\nmemories = {flag}\n", encoding="utf-8")
    return config_dir


def _find_secret(text: str) -> str | None:
    found = detect(text)
    return found[0].rule if found else None


@dataclass
class Machine:
    """One machine: its id, its agents and its ledger, over the shared vault."""

    machine_id: str
    root: pathlib.Path
    agents: list[AgentSource] = field(default_factory=list)
    audit: FakeAudit = field(default_factory=FakeAudit)
    threshold: int = 50
    home: str = ""

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.home = self.home or os.environ["HOME"]
        self.service = MemorySyncService(
            agents=self._list,
            readers={r.agent_type: r for r in MEMORY_READERS},
            writers={w.agent_type: w for w in MEMORY_WRITERS},
            audit=self.audit,
            machine=lambda: self.machine_id,
            home=lambda: self.home,
            find_secret=_find_secret,
            ledger=LedgerStore(lambda: self.root / "memory-sync.json"),
            previews=PreviewStore(lambda: self.root / "memory-sync-preview.json"),
            threshold=self.threshold,
        )
        self.launched: list[tuple[str, str, str]] = []

        async def _launch(agent_type: str, config_dir: str, home: str) -> bool:
            self.launched.append((agent_type, config_dir, home))
            return True

        self.view = MemorySyncView(
            self.service,
            machine=lambda: self.machine_id,
            home=lambda: self.home,
            audit=self.audit,
            launch=_launch,
        )

    async def _list(self) -> list[AgentSource]:
        return list(self.agents)

    def claude(self, name: str = "cc") -> pathlib.Path:
        config = self.root / f"claude-{name}"
        config.mkdir(parents=True, exist_ok=True)
        self.agents.append(
            AgentSource(agent=name, agent_type="claude_code", config_dir=str(config))
        )
        return config

    def codex(self, name: str = "codex", **kwargs: object) -> pathlib.Path:
        config = self.root / f"codex-{name}"
        codex_dir(config, **kwargs)  # type: ignore[arg-type]
        self.agents.append(AgentSource(agent=name, agent_type="codex", config_dir=str(config)))
        return config

    async def sync(self, actor: str = "user") -> object:
        """Sync, writing past the first-sync preview the way a person would."""
        report = await self.service.sync(actor)
        if self.service.previews.load() is not None:
            report = await self.service.write_preview(actor)
        return report


def hub_files(vault: pathlib.Path) -> list[pathlib.Path]:
    root = vault / "memory"
    return sorted(p for p in root.rglob("*.md")) if root.is_dir() else []


__all__ = [
    "Machine",
    "cc_file",
    "cc_memory_dir",
    "cc_project",
    "cc_slug",
    "codex_dir",
    "codex_memory",
    "hub_files",
]
