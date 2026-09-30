"""Finding hand edits once they are quiet, and history / diff / restore of any
vault file (coffer.infrastructure.vault.scanner, coffer.application.vault.history_service)."""

from __future__ import annotations

import pytest

from coffer.application.vault.history_service import VaultHistoryService, VaultVersionNotFound
from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.writers import WRITER_DISK, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.scanner import VaultScanner
from coffer.infrastructure.vault.writer import VaultWriter

USER = CommitMeta(writer=WRITER_USER, operation="save", summary="Saved", actor="user")


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_an_edit_is_settled_only_after_it_has_been_quiet(
    repo: VaultRepository, writer: VaultWriter
) -> None:
    clock = _Clock()
    scanner = VaultScanner(writer, quiet=1.0, watch=False, clock=clock)
    path = repo.root / "knowledge" / "a.md"
    path.parent.mkdir()
    path.write_bytes(b"typing\n")
    assert scanner.tick() is None  # first look records
    clock.now += 0.5
    path.write_bytes(b"typing more\n")
    assert scanner.tick() is None  # changed again: not quiet
    clock.now += 1.5
    result = scanner.tick()
    assert result is not None and result.meta.writer == WRITER_DISK
    assert repo.read("HEAD", "knowledge/a.md") == b"typing more\n"


def test_the_boot_scan_settles_everything_at_once(
    repo: VaultRepository, writer: VaultWriter
) -> None:
    (repo.root / "knowledge").mkdir()
    (repo.root / "knowledge" / "down.md").write_bytes(b"edited while the daemon was down\n")
    scanner = VaultScanner(writer, watch=False)
    assert scanner.boot_scan() is not None
    assert writer.pending() == {}


@pytest.fixture
def history(repo: VaultRepository, writer: VaultWriter) -> VaultHistoryService:
    return VaultHistoryService(repo, writer)


async def test_a_files_history_is_newest_first_with_its_writers(
    history: VaultHistoryService, writer: VaultWriter
) -> None:
    writer.write_file("skills/pdf/SKILL.md", b"v1\n", meta=USER, expected=Expect.ABSENT)
    writer.write_file("skills/pdf/SKILL.md", b"v2\n", meta=USER)
    page = await history.versions("skills/pdf/SKILL.md")
    assert [v.commit.meta.summary for v in page.versions] == ["Saved", "Saved"]
    assert page.next_cursor is None
    one = await history.versions("skills/pdf/SKILL.md", limit=1)
    assert one.next_cursor == "1" and len(one.versions) == 1
    folder = await history.versions("skills/pdf/")
    assert len(folder.versions) == 2


async def test_a_version_diff_and_its_content(
    history: VaultHistoryService, writer: VaultWriter
) -> None:
    first = writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    second = writer.write_file("knowledge/a.md", b"two\n", meta=USER)
    assert first and second
    diff = await history.diff("knowledge/a.md", second)
    assert "-one" in diff.diff and "+two" in diff.diff
    assert await history.content("knowledge/a.md", first) == b"one\n"
    with pytest.raises(VaultVersionNotFound):
        await history.diff("knowledge/other.md", second)


async def test_restore_is_a_new_commit_through_the_same_checks(
    history: VaultHistoryService, writer: VaultWriter, repo: VaultRepository
) -> None:
    first = writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    writer.write_file("knowledge/a.md", b"two\n", meta=USER)
    assert first
    with pytest.raises(VaultFileStale):
        await history.restore(
            "knowledge/a.md", first, expected_fingerprint=fingerprint(b"one\n"), actor="user"
        )
    before = repo.head()
    done = await history.restore(
        "knowledge/a.md", first, expected_fingerprint=fingerprint(b"two\n"), actor="user"
    )
    assert done.version != before and repo.read("HEAD", "knowledge/a.md") == b"one\n"
    newest = repo.log(limit=1)[0]
    assert newest.meta.restored_from == first and newest.meta.operation == "restore"
    assert len(repo.log()) == 4  # baseline + two saves + the restore: nothing rewritten


async def test_restoring_a_folder_brings_back_its_files_and_removes_new_ones(
    history: VaultHistoryService, writer: VaultWriter, repo: VaultRepository
) -> None:
    v1 = writer.write_file("skills/pdf/SKILL.md", b"v1\n", meta=USER, expected=Expect.ABSENT)
    with writer.begin(USER) as txn:
        txn.write("skills/pdf/SKILL.md", b"v2\n")
        txn.write("skills/pdf/extra.py", b"x\n", Expect.ABSENT)
    assert v1
    await history.restore("skills/pdf/", v1, expected_fingerprint=None, actor="user")
    assert repo.tree("HEAD", "skills/pdf") == {
        "skills/pdf/SKILL.md": repo.tree(v1, "skills/pdf")["skills/pdf/SKILL.md"]
    }
