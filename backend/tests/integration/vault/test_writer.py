"""The vault's one write path: compare, write, validate, commit
(coffer.infrastructure.vault.writer)."""

from __future__ import annotations

import threading
from collections.abc import Sequence

import pytest

from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.errors import VaultFileStale, VaultValidationFailed
from coffer.domain.vault.findings import Finding, FindingCode
from coffer.domain.vault.writers import (
    WRITER_DAEMON,
    WRITER_DISK,
    WRITER_USER,
    CommitMeta,
)
from coffer.domain.vault.writes import Change, CommitResult, Expect, Fix, TreeReader, Verdict
from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.writer import VaultWriter

USER = CommitMeta(writer=WRITER_USER, operation="save", summary="Saved", actor="user")


def test_a_fresh_vault_is_a_repository_with_a_first_commit(repo: VaultRepository) -> None:
    assert repo.exists() and repo.head() is not None
    assert (repo.root / "manifest.json").read_text().strip().endswith("}")
    first = repo.log()[0]
    assert first.meta.writer == WRITER_DAEMON and first.meta.operation == "baseline"


def test_a_write_is_one_commit_naming_its_writer_and_machine(
    repo: VaultRepository, writer: VaultWriter
) -> None:
    version = writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    assert version == repo.head()
    commit = repo.log(limit=1)[0]
    assert commit.meta.writer == WRITER_USER and commit.meta.machine == "machine-1"
    assert [p.path for p in commit.paths] == ["knowledge/a.md"]
    assert repo.read("HEAD", "knowledge/a.md") == b"one\n"


@pytest.mark.acceptance(spec="vault-sync", scenario="an unchanged vault serializes to an identical tree")
def test_a_write_that_changes_nothing_makes_no_commit(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    head = repo.head()
    assert writer.write_file("knowledge/a.md", b"one\n", meta=USER) is None
    assert repo.head() == head


def test_a_stale_fingerprint_is_refused_and_nothing_changes(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    with pytest.raises(VaultFileStale):
        writer.write_file("knowledge/a.md", b"two\n", meta=USER, expected=fingerprint(b"other"))
    assert (repo.root / "knowledge/a.md").read_bytes() == b"one\n"
    writer.write_file("knowledge/a.md", b"two\n", meta=USER, expected=fingerprint(b"one\n"))
    assert repo.read("HEAD", "knowledge/a.md") == b"two\n"


def test_a_concurrent_hand_edit_is_refused_rather_than_lost(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    (repo.root / "knowledge/a.md").write_bytes(b"a person's edit\n")
    with pytest.raises(VaultFileStale, match="not settled"):
        writer.write_file("knowledge/a.md", b"daemon\n", meta=USER, expected=Expect.HEAD)
    assert (repo.root / "knowledge/a.md").read_bytes() == b"a person's edit\n"


def _refuse_bad(changes: Sequence[Change], _repo: TreeReader) -> Verdict:
    return Verdict(
        findings=[
            Finding(c.path, FindingCode.INVALID_DOCUMENT, "bad")
            for c in changes
            if c.data is not None and b"bad" in c.data
        ]
    )


def test_an_invalid_write_is_undone_and_head_stays(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.set_validator(_refuse_bad)
    writer.write_file("state/x/a.json", b"good\n", meta=USER, expected=Expect.ABSENT)
    head = repo.head()
    with pytest.raises(VaultValidationFailed):
        writer.write_file("state/x/a.json", b"bad\n", meta=USER)
    assert repo.head() == head
    assert (repo.root / "state/x/a.json").read_bytes() == b"good\n"


def test_an_operation_is_one_commit_however_many_files(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    with writer.begin(USER) as txn:
        txn.write("skills/pdf/SKILL.md", b"---\nname: pdf\n---\n", Expect.ABSENT)
        txn.write("skills/pdf/scripts/x.py", b"print(1)\n", Expect.ABSENT)
    commit = repo.log(limit=1)[0]
    assert sorted(p.path for p in commit.paths) == [
        "skills/pdf/SKILL.md",
        "skills/pdf/scripts/x.py",
    ]


def test_a_failed_operation_puts_every_file_back(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    head = repo.head()
    with pytest.raises(RuntimeError), writer.begin(USER) as txn:
        txn.write("knowledge/a.md", b"two\n")
        txn.write("knowledge/b.md", b"new\n", Expect.ABSENT)
        raise RuntimeError("boom")
    assert repo.head() == head
    assert (repo.root / "knowledge/a.md").read_bytes() == b"one\n"
    assert not (repo.root / "knowledge/b.md").exists()


def test_an_owned_path_is_neither_settled_nor_written_by_another_operation(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    long = writer.begin(CommitMeta(writer="curation", operation="pass", summary="pass"))
    long.write("knowledge/a.md", b"curated\n", Expect.ABSENT)
    assert "knowledge/a.md" not in writer.pending()
    assert writer.settle() is None
    with pytest.raises(VaultFileStale, match="another operation"):
        writer.write_file("knowledge/a.md", b"x\n", meta=USER, expected=Expect.HEAD)
    assert long.commit() is not None
    assert repo.log(limit=1)[0].meta.writer == "curation"


def test_settle_commits_valid_hand_edits_and_keeps_invalid_ones_uncommitted(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.set_validator(_refuse_bad)
    (repo.root / "knowledge").mkdir(exist_ok=True)
    (repo.root / "knowledge/ok.md").write_bytes(b"fine\n")
    (repo.root / "knowledge/no.md").write_bytes(b"bad\n")
    result = writer.settle()
    assert result is not None and result.paths == ("knowledge/ok.md",)
    assert result.meta.writer == WRITER_DISK
    assert repo.read("HEAD", "knowledge/no.md") is None
    assert (repo.root / "knowledge/no.md").read_bytes() == b"bad\n"
    assert list(writer.problems()) == ["knowledge/no.md"]
    (repo.root / "knowledge/no.md").write_bytes(b"fixed\n")
    writer.settle()
    assert writer.problems() == {}


def test_a_fix_the_validator_asks_for_follows_as_a_daemon_commit(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    def mint(changes: Sequence[Change], _repo: TreeReader) -> Verdict:
        return Verdict(
            fixes=[
                Fix(c.path, c.data + b"uid\n", "Gave it a uid")
                for c in changes
                if c.data is not None and b"uid" not in c.data
            ]
        )

    writer.set_validator(mint)
    (repo.root / "resources/skill").mkdir(parents=True)
    (repo.root / "resources/skill/x.json").write_bytes(b"hand\n")
    writer.settle()
    two = repo.log(limit=2)
    assert [c.meta.writer for c in two] == [WRITER_DAEMON, WRITER_DISK]
    assert repo.read("HEAD", "resources/skill/x.json") == b"hand\nuid\n"


def test_listeners_hear_every_commit(writer: VaultWriter) -> None:
    heard: list[CommitResult] = []
    writer.add_listener(heard.append)
    writer.write_file("knowledge/a.md", b"one\n", meta=USER, expected=Expect.ABSENT)
    assert [r.paths for r in heard] == [("knowledge/a.md",)]


@pytest.mark.acceptance(spec="vault-sync", scenario="ciphertext travels only when the remote carries it")
def test_credentials_are_never_committed_unless_carried(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    writer.write_file("secret/ref.enc", b"gAAAA\n", meta=USER, expected=Expect.ABSENT)
    assert repo.read("HEAD", "secret/ref.enc") is None
    assert "secret/ref.enc" not in writer.pending()
    repo.set_carry_secret(True)
    writer.settle()
    assert repo.read("HEAD", "secret/ref.enc") == b"gAAAA\n"


def test_writers_in_parallel_threads_each_land_whole(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    def put(i: int) -> None:
        writer.write_file(f"knowledge/{i}.md", f"{i}\n".encode(), meta=USER, expected=Expect.ABSENT)

    threads = [threading.Thread(target=put, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(repo.tree("HEAD", "knowledge")) == sorted(f"knowledge/{i}.md" for i in range(8))
    assert writer.pending() == {}


@pytest.mark.acceptance(spec="vault-sync", scenario="a symlink in the vault is skipped rather than published")
def test_symlinks_and_nested_repositories_are_never_recorded(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    import os
    import subprocess

    (repo.root / "skills/pdf").mkdir(parents=True)
    (repo.root / "skills/pdf/SKILL.md").write_bytes(b"---\nname: pdf\n---\n")
    os.symlink("/etc/hosts", repo.root / "skills/pdf/hosts")
    nested = repo.root / "skills/vendored"
    nested.mkdir()
    subprocess.run(["git", "init", "-q", str(nested)], check=True)
    (nested / "x.txt").write_bytes(b"x\n")
    writer.settle()
    assert set(repo.tree("HEAD", "skills")) == {"skills/pdf/SKILL.md"}
    assert writer.pending() == {}
