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

from coffer.application.memory.sources import AgentSource
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


@dataclass(frozen=True)
class CodexMemory:
    """Codex's v2 memory as a test writes it: the summary and, per rollout
    summary file, the working directory its header records."""

    summary: str
    rollouts: dict[str, str]


def codex_topics(groups: Sequence[tuple[str, str, Sequence[str]]]) -> CodexMemory:
    """Codex's v2 memory holding ``(scope, cwd, topics)``: each topic is one
    bullet of ``What's in Memory`` under its scope, pointing at a rollout
    summary recorded in ``cwd`` (no pointer when ``cwd`` is empty)."""
    lines = ["v1", "", "## What's in Memory", ""]
    rollouts: dict[str, str] = {}
    for n, (scope, cwd, topics) in enumerate(groups):
        name = f"r{n}.md"
        if cwd:
            rollouts[name] = cwd
        lines += [f"### {scope}", "#### 2026-11-02"]
        for i, topic in enumerate(topics):
            pointer = f"rollout_summaries/{name} — " if cwd else ""
            lines.append(f"- {pointer}{topic}; thread_id=t-{n}-{i}")
        lines.append("")
    return CodexMemory("\n".join(lines), rollouts)


def write_codex_memory(config_dir: pathlib.Path, memory: CodexMemory) -> None:
    """Write (or rewrite) ``config_dir``'s v2 memory."""
    v2 = config_dir / "memories_v2"
    (v2 / "rollout_summaries").mkdir(parents=True, exist_ok=True)
    (v2 / "memory_summary.md").write_text(memory.summary, encoding="utf-8")
    for name, cwd in memory.rollouts.items():
        (v2 / "rollout_summaries" / name).write_text(
            f"thread_id: t-{name}\nupdated_at: 2026-11-02T09:22:08+00:00\n"
            f"rollout_path: /sessions/{name}.jsonl\ncwd: {cwd}\n\nWhat happened.\n",
            encoding="utf-8",
        )


def codex_dir(
    config_dir: pathlib.Path,
    memory: CodexMemory | None = None,
    *,
    memories_on: bool = True,
    v1: bool = True,
    v2: bool = False,
) -> pathlib.Path:
    """A Codex config directory: an empty v1 folder (``memories/``, which
    Coffer writes into and never reads) unless ``v1`` is false, and a v2
    folder (``memories_v2/``) holding ``memory`` when one is given or ``v2``
    is true."""
    config_dir.mkdir(parents=True, exist_ok=True)
    if v1:
        memories = config_dir / "memories"
        memories.mkdir(parents=True, exist_ok=True)
        (memories / "MEMORY.md").write_text("", encoding="utf-8")
    if memory is not None or v2:
        write_codex_memory(config_dir, memory or CodexMemory("v1\n", {}))
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
        self.view = MemorySyncView(
            self.service,
            machine=lambda: self.machine_id,
            home=lambda: self.home,
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
    """The hub's memory files."""
    root = vault / "memory"
    return sorted(root.rglob("*.md")) if root.is_dir() else []


def resources(codex: pathlib.Path) -> list[pathlib.Path]:
    """The copies Coffer wrote into Codex's memory extension."""
    folder = codex / "memories" / "extensions" / "coffer" / "resources"
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


__all__ = [
    "CodexMemory",
    "Machine",
    "cc_file",
    "cc_memory_dir",
    "cc_project",
    "cc_slug",
    "codex_dir",
    "codex_topics",
    "hub_files",
    "resources",
    "write_codex_memory",
]
