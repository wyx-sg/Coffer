"""Finding hand edits once they are quiet (coffer.infrastructure.vault.scanner),
and a version written back as a restore, which is a new commit that rewrites no
history (spec vault-storage "Show and restore any version of a vault file or
folder")."""

from __future__ import annotations

import pytest

from coffer.domain.vault.writers import (
    OP_RESTORE,
    WRITER_AGENT,
    WRITER_DISK,
    WRITER_USER,
    CommitMeta,
)
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


@pytest.mark.acceptance(spec="vault-storage", scenario="an edit is committed once it is quiet")
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


@pytest.mark.acceptance(
    spec="vault-sync", scenario="restore brings back a document deleted last week"
)
def test_a_version_written_back_as_a_restore_is_a_new_commit(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    first = writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    writer.write_file("knowledge/a.md", b"two\n", meta=USER)
    assert first
    before = [c.version for c in repo.log()]

    restore = CommitMeta(
        writer=WRITER_AGENT,
        operation=OP_RESTORE,
        summary="Restored knowledge/a.md",
        restored_from=first,
    )
    done = writer.write_file(
        "knowledge/a.md", repo.read(first, "knowledge/a.md") or b"", meta=restore
    )

    assert done is not None and done not in before
    assert repo.read("HEAD", "knowledge/a.md") == b"one\n"
    newest = repo.log(limit=1)[0]
    assert newest.meta.restored_from == first and newest.meta.operation == OP_RESTORE
    # baseline + two saves + the restore: no earlier commit was rewritten.
    assert [c.version for c in repo.log()][1:] == before
