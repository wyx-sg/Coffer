"""Unit tests for AgentConfigFileService (the config-file listing).

Uses a fake ConfigFileStorePort (dict-backed, no real FS) and a fake
_AgentLookup to keep this tier pure Python with no I/O. Covers the listing:
a directory entry with its files and exists semantics, and a file entry's kind.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.domain.agent.config_files import DirEntryInfo, FileStat
from coffer.domain.resource import Resource

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

# Minimal in-memory agent config that looks like a registered claude_code agent
# pointing at a stable config dir.
_CLAUDE_CONFIG_DIR = pathlib.Path("/fake/home/.claude")

# The agent is addressed by its uid; "cc" is only the label the row carries.
_CLAUDE_UID = "7c1f0a9b4e2d4f3a8b6c5d0e1f2a3b4c"

_CLAUDE_RESOURCE = Resource(
    uid=_CLAUDE_UID,
    kind="agent",
    name="cc",
    description=None,
    config={
        "type": "claude_code",
        "config_dir": str(_CLAUDE_CONFIG_DIR),
    },
    enabled=True,
    created_at=_NOW,
    updated_at=_NOW,
)


class FakeAgentLookup:
    """Returns a hard-coded Resource for one uid; raises for anything else."""

    async def get(self, uid: str) -> Resource:
        if uid == _CLAUDE_UID:
            return _CLAUDE_RESOURCE
        from coffer.domain.errors import ResourceNotFound

        raise ResourceNotFound(uid)


@dataclass
class FakeStore:
    """In-memory store. Files are stored in `_files`; dirs in `_dirs`."""

    _files: dict[pathlib.Path, str] = field(default_factory=dict)
    # dirs maps a root Path → list of DirEntryInfo (None means root doesn't exist)
    _dirs: dict[pathlib.Path, list[DirEntryInfo] | None] = field(default_factory=dict)

    def read_text(self, path: pathlib.Path) -> str | None:
        return self._files.get(path)

    def stat(self, path: pathlib.Path) -> FileStat | None:
        text = self._files.get(path)
        if text is None:
            return None
        return FileStat(size=len(text.encode()), modified_at=_NOW)

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        self._files[path] = text

    def list_dir(self, root: pathlib.Path) -> list[DirEntryInfo] | None:
        return self._dirs.get(root)

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        return self._files.pop(path, None) is not None

    def fingerprint(self, text: str | None) -> str:
        if text is None:
            return ""
        return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store() -> FakeStore:
    s = FakeStore()
    # Pre-seed the subagents directory as an existing (empty) directory.
    agents_dir = _CLAUDE_CONFIG_DIR / "agents"
    s._dirs[agents_dir] = []
    return s


@pytest_asyncio.fixture
async def svc(store) -> AgentConfigFileService:
    return AgentConfigFileService(agent_service=FakeAgentLookup(), store=store)


# ---------------------------------------------------------------------------
# list_files includes directory entry with kind + files
# ---------------------------------------------------------------------------


async def test_list_includes_directory_entry_with_files(svc, store):
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "helper.md"
    store._files[child_path] = "# Helper"
    store._dirs[_CLAUDE_CONFIG_DIR / "agents"] = [
        DirEntryInfo(relpath="helper.md", path=str(child_path), size=8, modified_at=_NOW)
    ]

    files = await svc.list_files(_CLAUDE_UID)
    by_key = {f.key: f for f in files}

    assert "subagents" in by_key
    entry = by_key["subagents"]
    assert entry.kind == "directory"
    assert entry.exists is True  # listing is not None
    assert entry.files is not None
    assert len(entry.files) == 1
    assert entry.files[0].relpath == "helper.md"
    assert entry.files[0].path == str(child_path)
    assert entry.size is None
    assert entry.modified_at is None


async def test_list_directory_entry_missing_dir(svc, store):
    # Remove the pre-seeded directory listing so it returns None.
    store._dirs.pop(_CLAUDE_CONFIG_DIR / "agents", None)

    files = await svc.list_files(_CLAUDE_UID)
    by_key = {f.key: f for f in files}
    entry = by_key["subagents"]
    assert entry.kind == "directory"
    assert entry.exists is False
    assert entry.files is None


async def test_list_file_entry_has_file_kind(svc, store):
    files = await svc.list_files(_CLAUDE_UID)
    by_key = {f.key: f for f in files}
    assert by_key["settings"].kind == "file"
