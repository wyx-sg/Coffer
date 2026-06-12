"""Unit tests for AgentConfigFileService v2.

Uses a fake ConfigFileStorePort (dict-backed, no real FS) and a fake
_AgentLookup to keep this tier pure Python with no I/O.

Covers:
  1. list includes kind="directory" entry with files populated and exists semantics
  2. read_file returns fingerprint + memory_block=True when content contains the marker
  3. read_file on a directory key → ConfigFileNotAllowed
  4. write_file with stale fingerprint → ConfigFileStale, store NOT written;
     with matching fingerprint → success
  5. read_child/write_child/delete_child happy path incl. audit event names + details
  6. write_child on FILE entry → ConfigFileNotAllowed;
     delete_child missing file → ConfigFileNotAllowed
  7. child relpath traversal (../x.md) → ConfigFileNotAllowed (no store call)
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from coffer.application.agent.config_file_service import (
    MEMORY_BLOCK_MARKER,
    AgentConfigFileService,
)
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config_files import DirEntryInfo, FileStat
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileNotAllowed, ConfigFileStale
from coffer.domain.resource import Resource

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

# Minimal in-memory agent config that looks like a registered claude_code agent
# pointing at a stable config dir.
_CLAUDE_CONFIG_DIR = pathlib.Path("/fake/home/.claude")

_CLAUDE_RESOURCE = Resource(
    id=1,
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
    """Returns a hard-coded Resource for 'cc'; raises for anything else."""

    async def get(self, name: str) -> Resource:
        if name == "cc":
            return _CLAUDE_RESOURCE
        from coffer.domain.errors import ResourceNotFound

        raise ResourceNotFound("agent", name)


@dataclass
class FakeStore:
    """In-memory store. Files are stored in `_files`; dirs in `_dirs`."""

    _files: dict[pathlib.Path, str] = field(default_factory=dict)
    # dirs maps a root Path → list of DirEntryInfo (None means root doesn't exist)
    _dirs: dict[pathlib.Path, list[DirEntryInfo] | None] = field(default_factory=dict)
    _writes: list[tuple[pathlib.Path, str]] = field(default_factory=list)
    _deletes: list[pathlib.Path] = field(default_factory=list)
    # Tests opt into simulating a symlink escape by listing paths here.
    escaping_paths: set[pathlib.Path] = field(default_factory=set)

    # --- port methods ---

    def read_text(self, path: pathlib.Path) -> str | None:
        return self._files.get(path)

    def stat(self, path: pathlib.Path) -> FileStat | None:
        text = self._files.get(path)
        if text is None:
            return None
        return FileStat(size=len(text.encode()), modified_at=_NOW)

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        self._writes.append((path, text))
        self._files[path] = text
        # Refresh directory listing if the parent is tracked.
        for root, listing in list(self._dirs.items()):
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            # Re-build the listing for this root.
            if listing is None:
                self._dirs[root] = []
                listing = self._dirs[root]
            relpath_str = rel.as_posix()
            existing = [e for e in listing if e.relpath != relpath_str]
            size = len(text.encode())
            existing.append(DirEntryInfo(relpath=relpath_str, size=size, modified_at=_NOW))
            self._dirs[root] = sorted(existing, key=lambda e: e.relpath)

    def list_dir(self, root: pathlib.Path) -> list[DirEntryInfo] | None:
        return self._dirs.get(root)

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        if path not in self._files:
            return False
        self._deletes.append(path)
        del self._files[path]
        # Remove from directory listing.
        for root, listing in list(self._dirs.items()):
            if listing is None:
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            relpath_str = rel.as_posix()
            self._dirs[root] = [e for e in listing if e.relpath != relpath_str]
        return True

    def fingerprint(self, text: str | None) -> str:
        if text is None:
            return ""
        return hashlib.sha256(text.encode()).hexdigest()

    def resolved_within(self, path: pathlib.Path, root: pathlib.Path) -> bool:
        # Pure-dict fake has no symlinks; tests opt into escape via this flag.
        return path not in self.escaping_paths


class FakeAuditRepo:
    def __init__(self) -> None:
        self._entries: list = []

    async def insert(self, entry) -> None:
        self._entries.append(entry)

    async def query(
        self,
        *,
        kind=None,
        name=None,
        event_type=None,
        since=None,
        limit=50,
    ):
        results = self._entries
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        return results[:limit]


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
async def audit_svc(store) -> AuditService:
    return AuditService(FakeAuditRepo())


@pytest_asyncio.fixture
async def svc(store, audit_svc) -> AgentConfigFileService:
    return AgentConfigFileService(
        agent_service=FakeAgentLookup(),
        audit=audit_svc,
        store=store,
    )


# ---------------------------------------------------------------------------
# Test 1: list_files includes directory entry with kind + files
# ---------------------------------------------------------------------------


async def test_list_includes_directory_entry_with_files(svc, store):
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "helper.md"
    store._files[child_path] = "# Helper"
    store._dirs[_CLAUDE_CONFIG_DIR / "agents"] = [
        DirEntryInfo(relpath="helper.md", size=8, modified_at=_NOW)
    ]

    files = await svc.list_files("cc")
    by_key = {f.key: f for f in files}

    assert "subagents" in by_key
    entry = by_key["subagents"]
    assert entry.kind == "directory"
    assert entry.exists is True  # listing is not None
    assert entry.files is not None
    assert len(entry.files) == 1
    assert entry.files[0].relpath == "helper.md"
    assert entry.size is None
    assert entry.modified_at is None


async def test_list_directory_entry_missing_dir(svc, store):
    # Remove the pre-seeded directory listing so it returns None.
    store._dirs.pop(_CLAUDE_CONFIG_DIR / "agents", None)

    files = await svc.list_files("cc")
    by_key = {f.key: f for f in files}
    entry = by_key["subagents"]
    assert entry.kind == "directory"
    assert entry.exists is False
    assert entry.files is None


async def test_list_file_entry_has_file_kind(svc, store):
    files = await svc.list_files("cc")
    by_key = {f.key: f for f in files}
    assert by_key["settings"].kind == "file"


# ---------------------------------------------------------------------------
# Test 2: read_file returns fingerprint + memory_block
# ---------------------------------------------------------------------------


async def test_read_file_returns_fingerprint_and_no_memory_block(svc, store):
    settings_path = _CLAUDE_CONFIG_DIR / "settings.json"
    store._files[settings_path] = '{"theme": "dark"}'

    out = await svc.read_file("cc", "settings")
    assert out.fingerprint == store.fingerprint('{"theme": "dark"}')
    assert out.memory_block is False


async def test_read_file_detects_memory_block_marker(svc, store):
    instructions_path = _CLAUDE_CONFIG_DIR / "CLAUDE.md"
    content = f"# Rules\n\n{MEMORY_BLOCK_MARKER} -->\nsome block\n<!-- end -->"
    store._files[instructions_path] = content

    out = await svc.read_file("cc", "instructions")
    assert out.memory_block is True
    assert out.fingerprint == store.fingerprint(content)


async def test_read_file_missing_gives_empty_fingerprint(svc, store):
    out = await svc.read_file("cc", "settings")
    assert out.exists is False
    assert out.fingerprint == ""
    assert out.memory_block is False


# ---------------------------------------------------------------------------
# Test 3: read_file on a directory key → ConfigFileNotAllowed
# ---------------------------------------------------------------------------


async def test_read_file_directory_key_raises_not_allowed(svc):
    with pytest.raises(ConfigFileNotAllowed):
        await svc.read_file("cc", "subagents")


# ---------------------------------------------------------------------------
# Test 4: write_file stale check
# ---------------------------------------------------------------------------


async def test_write_file_stale_fingerprint_raises_and_no_write(svc, store):
    settings_path = _CLAUDE_CONFIG_DIR / "settings.json"
    store._files[settings_path] = '{"theme": "light"}'

    before_writes = len(store._writes)
    with pytest.raises(ConfigFileStale):
        await svc.write_file(
            "cc",
            "settings",
            '{"theme": "dark"}',
            expected_fingerprint="wrong-fingerprint",
        )
    assert len(store._writes) == before_writes  # store was NOT written


async def test_write_file_matching_fingerprint_succeeds(svc, store):
    settings_path = _CLAUDE_CONFIG_DIR / "settings.json"
    current_text = '{"theme": "light"}'
    store._files[settings_path] = current_text
    correct_fp = store.fingerprint(current_text)

    info = await svc.write_file(
        "cc",
        "settings",
        '{"theme": "dark"}',
        expected_fingerprint=correct_fp,
    )
    assert info.exists is True
    assert store._files[settings_path] == '{"theme": "dark"}'


async def test_write_file_no_fingerprint_skips_stale_check(svc, store):
    # No expected_fingerprint → no stale check, always writes.
    info = await svc.write_file("cc", "settings", '{"a": 1}')
    assert info.exists is True


async def test_write_file_directory_key_raises_not_allowed(svc):
    with pytest.raises(ConfigFileNotAllowed):
        await svc.write_file("cc", "subagents", "# hi")


# ---------------------------------------------------------------------------
# Test 5: read_child / write_child / delete_child happy paths + audit events
# ---------------------------------------------------------------------------


async def test_read_child_missing_returns_empty(svc, store):
    out = await svc.read_child("cc", "subagents", "helper.md")
    assert out.exists is False
    assert out.content == ""
    assert out.fingerprint == ""
    assert out.memory_block is False


async def test_read_child_existing(svc, store):
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "helper.md"
    store._files[child_path] = "# Helper"

    out = await svc.read_child("cc", "subagents", "helper.md")
    assert out.exists is True
    assert out.content == "# Helper"
    assert out.fingerprint == store.fingerprint("# Helper")


async def test_write_child_happy_path_and_audit(svc, store, audit_svc):
    info = await svc.write_child("cc", "subagents", "new.md", "# New", actor="cli")

    # Returns refreshed directory listing.
    assert info.kind == "directory"
    assert info.files is not None
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "new.md"
    assert store._files[child_path] == "# New"

    # Audit event was recorded.
    entries = await audit_svc.query()
    assert len(entries) == 1
    assert entries[0].event_type == AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value
    assert entries[0].details == {"key": "subagents", "child": "new.md"}


async def test_delete_child_happy_path_and_audit(svc, store, audit_svc):
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "old.md"
    store._files[child_path] = "# Old"
    store._dirs[_CLAUDE_CONFIG_DIR / "agents"] = [
        DirEntryInfo(relpath="old.md", size=5, modified_at=_NOW)
    ]

    await svc.delete_child("cc", "subagents", "old.md", actor="cli")

    assert child_path not in store._files
    entries = await audit_svc.query()
    assert len(entries) == 1
    assert entries[0].event_type == AuditEventType.AGENT_CONFIG_FILE_DELETED.value
    assert entries[0].details == {"key": "subagents", "child": "old.md"}


async def test_write_child_stale_raises_no_write(svc, store):
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "helper.md"
    store._files[child_path] = "# Original"

    before_writes = len(store._writes)
    with pytest.raises(ConfigFileStale):
        await svc.write_child(
            "cc", "subagents", "helper.md", "# Modified", expected_fingerprint="bad-fp"
        )
    assert len(store._writes) == before_writes


async def test_write_child_matching_fingerprint_succeeds(svc, store):
    child_path = _CLAUDE_CONFIG_DIR / "agents" / "helper.md"
    store._files[child_path] = "# Original"
    fp = store.fingerprint("# Original")

    await svc.write_child("cc", "subagents", "helper.md", "# Updated", expected_fingerprint=fp)
    assert store._files[child_path] == "# Updated"


# ---------------------------------------------------------------------------
# Test 6: write_child on FILE key → ConfigFileNotAllowed;
#          delete_child missing file → ConfigFileNotAllowed
# ---------------------------------------------------------------------------


async def test_write_child_on_file_key_raises(svc):
    with pytest.raises(ConfigFileNotAllowed):
        await svc.write_child("cc", "settings", "x.md", "# x")


async def test_read_child_on_file_key_raises(svc):
    with pytest.raises(ConfigFileNotAllowed):
        await svc.read_child("cc", "settings", "x.md")


async def test_delete_child_missing_file_raises(svc, store):
    # The agents directory exists but 'ghost.md' is not in it.
    with pytest.raises(ConfigFileNotAllowed):
        await svc.delete_child("cc", "subagents", "ghost.md")


async def test_delete_child_on_file_key_raises(svc):
    with pytest.raises(ConfigFileNotAllowed):
        await svc.delete_child("cc", "settings", "x.md")


# ---------------------------------------------------------------------------
# Test 7: child relpath traversal → ConfigFileNotAllowed (no store call)
# ---------------------------------------------------------------------------


async def test_read_child_traversal_rejected(svc, store):
    before = len(store._writes)
    with pytest.raises(ConfigFileNotAllowed):
        await svc.read_child("cc", "subagents", "../secret.md")
    # No filesystem access happened.
    assert len(store._writes) == before


async def test_write_child_traversal_rejected(svc, store):
    before = len(store._writes)
    with pytest.raises(ConfigFileNotAllowed):
        await svc.write_child("cc", "subagents", "../escape.md", "# bad")
    assert len(store._writes) == before


async def test_delete_child_traversal_rejected(svc, store):
    before = len(store._deletes)
    with pytest.raises(ConfigFileNotAllowed):
        await svc.delete_child("cc", "subagents", "../escape.md")
    assert len(store._deletes) == before


async def test_write_child_absolute_relpath_rejected(svc):
    with pytest.raises(ConfigFileNotAllowed):
        await svc.write_child("cc", "subagents", "/etc/passwd.md", "# bad")


@pytest.mark.asyncio
async def test_child_symlink_escape_rejected(svc, store) -> None:
    store.escaping_paths.add(_CLAUDE_CONFIG_DIR / "agents" / "evil.md")
    with pytest.raises(ConfigFileNotAllowed):
        await svc.read_child("cc", "subagents", "evil.md")
    with pytest.raises(ConfigFileNotAllowed):
        await svc.write_child("cc", "subagents", "evil.md", "# x", actor="api")
