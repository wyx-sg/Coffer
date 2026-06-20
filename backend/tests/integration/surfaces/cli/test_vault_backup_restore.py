"""Integration tests for ``coffer backup`` / ``coffer restore`` (vault-level).

These are offline, filesystem-only operations: they capture and re-place the
whole vault (``coffer.db`` + the knowledge / memory / skills file trees) without
talking to the daemon, so a backup is portable and a restore works on a fresh
machine before any daemon exists.
"""

from __future__ import annotations

import sqlite3
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

_runner = CliRunner()


def _populate_vault(home: Path) -> None:
    """Create a populated ``~/.coffer`` vault: db + knowledge + memory + skills."""
    coffer = home / ".coffer"
    coffer.mkdir(parents=True, exist_ok=True)

    # The rebuildable index.
    db = coffer / "coffer.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE chunk (id INTEGER, body TEXT);")
    conn.execute("INSERT INTO chunk VALUES (1, 'indexed-from-markdown');")
    conn.commit()
    conn.close()

    # The system of record: markdown trees.
    kb_doc = coffer / "knowledge" / "handbook" / "docs" / "welcome.md"
    kb_doc.parent.mkdir(parents=True, exist_ok=True)
    kb_doc.write_text("# Welcome\n\nThe sky is blue.\n", encoding="utf-8")

    mem_fact = coffer / "memory" / "global" / "prefers-dark-mode.md"
    mem_fact.parent.mkdir(parents=True, exist_ok=True)
    mem_fact.write_text("User prefers dark mode.\n", encoding="utf-8")

    skill = coffer / "skills" / "greet" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("# greet\n", encoding="utf-8")

    # The Fernet master key — secret material that must NOT travel by default.
    (coffer / "master.key").write_bytes(b"super-secret-fernet-key==")


@pytest.mark.acceptance(
    spec="001-mcp-gateway",
    scenario="vault backup captures db + file trees, restore round-trips them",
)
def test_backup_then_restore_round_trips_db_and_file_trees(tmp_path, monkeypatch):
    """Backup a populated vault, restore into an empty one, assert full fidelity."""
    src_home = tmp_path / "src_home"
    dest = tmp_path / "coffer-backup.tar.gz"
    restore_home = tmp_path / "restore_home"
    restore_home.mkdir(parents=True)

    monkeypatch.setenv("HOME", str(src_home))
    _populate_vault(src_home)

    result = _runner.invoke(app, ["backup", str(dest)])
    assert result.exit_code == 0, result.output
    assert "knowledge" in result.output and "memory" in result.output

    # The backup must be a single .tar.gz FILE (not a directory).
    assert dest.is_file(), "backup should be a .tar.gz file, not a directory"
    assert not dest.is_dir()

    # The archive must contain the file trees and db.
    with tarfile.open(dest, "r:gz") as tar:
        tar_names = set(tar.getnames())
    assert "coffer.db" in tar_names
    assert any(n.startswith("knowledge/") for n in tar_names)
    assert any(n.startswith("memory/") for n in tar_names)
    assert any(n.startswith("skills/") for n in tar_names)
    # master.key is excluded by default.
    assert "master.key" not in tar_names, "master.key must NOT be in archive by default"

    # Now restore into a fresh, empty HOME.
    monkeypatch.setenv("HOME", str(restore_home))
    result = _runner.invoke(app, ["restore", str(dest), "--force"])
    assert result.exit_code == 0, result.output

    coffer = restore_home / ".coffer"
    # DB round-trips with its row intact.
    conn = sqlite3.connect(coffer / "coffer.db")
    row = conn.execute("SELECT body FROM chunk WHERE id = 1;").fetchone()
    conn.close()
    assert row == ("indexed-from-markdown",)

    # KB doc and memory fact round-trip byte-for-byte.
    kb = coffer / "knowledge" / "handbook" / "docs" / "welcome.md"
    assert kb.read_text(encoding="utf-8") == "# Welcome\n\nThe sky is blue.\n"
    mem = coffer / "memory" / "global" / "prefers-dark-mode.md"
    assert mem.read_text(encoding="utf-8") == "User prefers dark mode.\n"
    assert (coffer / "skills" / "greet" / "SKILL.md").exists()


@pytest.mark.acceptance(
    spec="001-mcp-gateway",
    scenario="backup excludes the master key by default",
)
def test_backup_include_master_key_opt_in(tmp_path, monkeypatch):
    """``--include-master-key`` bundles the key and prints a loud warning."""
    src_home = tmp_path / "src_home"
    dest = tmp_path / "full-backup.tar.gz"
    monkeypatch.setenv("HOME", str(src_home))
    _populate_vault(src_home)

    result = _runner.invoke(app, ["backup", str(dest), "--include-master-key"])
    assert result.exit_code == 0, result.output

    # master.key must be a tar member when opt-in is used.
    with tarfile.open(dest, "r:gz") as tar:
        tar_names = set(tar.getnames())
    assert "master.key" in tar_names
    assert "WARNING" in result.output.upper()


def test_restore_is_atomic_on_failure(tmp_path, monkeypatch):
    """A mid-restore failure must NOT destroy the live source-of-record trees —
    the live vault is left exactly as it was, never half-overwritten."""
    from coffer.infrastructure.vault import backup as vault_backup

    src_home = tmp_path / "src"
    live_home = tmp_path / "live"
    backup = tmp_path / "backup.tar.gz"

    monkeypatch.setenv("HOME", str(src_home))
    _populate_vault(src_home)
    result = _runner.invoke(app, ["backup", str(backup)])
    assert result.exit_code == 0, result.output

    # A DIFFERENT populated live vault we are about to restore over.
    monkeypatch.setenv("HOME", str(live_home))
    _populate_vault(live_home)
    live_doc = live_home / ".coffer" / "knowledge" / "handbook" / "docs" / "welcome.md"
    live_doc.write_text("# LIVE — must survive a failed restore\n", encoding="utf-8")

    # Force the atomic swap to blow up partway (simulates an OS-level failure
    # after extraction but during the rename phase).
    import os as _os

    original_replace = _os.replace
    replace_calls = {"n": 0}

    def exploding_replace(src, dst):
        replace_calls["n"] += 1
        # Blow up on the second rename (first is the db; second is knowledge/).
        if replace_calls["n"] == 2:
            raise OSError(28, "No space left on device")
        return original_replace(src, dst)

    # Patch the reference used inside backup.py itself.
    monkeypatch.setattr(vault_backup.os, "replace", exploding_replace)

    with pytest.raises(OSError):
        vault_backup.restore_backup(backup)

    # The live tree is intact (not destroyed), and no staging/aside debris remains.
    assert live_doc.read_text(encoding="utf-8").startswith("# LIVE")
    coffer = live_home / ".coffer"
    assert not (coffer / ".restore-staging").exists()
    assert not (coffer / "knowledge.restore-old").exists()


def test_backup_refuses_when_no_vault(tmp_path, monkeypatch):
    """Backing up a non-existent vault is a clean error, not a traceback."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty_home"))
    result = _runner.invoke(app, ["backup", str(tmp_path / "out.tar.gz")])
    assert result.exit_code != 0
    assert "no" in result.output.lower() or "not" in result.output.lower()


def test_restore_refuses_invalid_archive(tmp_path, monkeypatch):
    """Restoring from a path with no coffer.db is rejected before clobbering."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    bogus = tmp_path / "not-a-backup.tar.gz"
    # Write a valid tar.gz but without coffer.db inside.
    import tarfile as _tarfile

    with _tarfile.open(bogus, "w:gz"):
        pass  # empty archive
    result = _runner.invoke(app, ["restore", str(bogus), "--force"])
    assert result.exit_code != 0
    assert "coffer.db" in result.output or "invalid" in result.output.lower()


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Minimal stand-in for the daemon HTTP client used by ``--reindex``."""

    def __init__(self) -> None:
        self.reindexed: list[str] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str) -> _FakeResponse:
        assert path == "/knowledge_bases"
        return _FakeResponse(200, {"knowledge_bases": [{"name": "handbook"}]})

    def post(self, path: str) -> _FakeResponse:
        assert path.endswith("/reindex")
        self.reindexed.append(path.split("/")[2])
        return _FakeResponse(200, {})


def test_restore_reindex_calls_daemon_per_kb(tmp_path, monkeypatch):
    """``restore --reindex`` rebuilds every KB's index via the daemon."""
    from coffer.surfaces.cli import _client as _cli_client

    src_home = tmp_path / "src_home"
    dest = tmp_path / "backup.tar.gz"
    monkeypatch.setenv("HOME", str(src_home))
    _populate_vault(src_home)
    assert _runner.invoke(app, ["backup", str(dest)]).exit_code == 0

    restore_home = tmp_path / "restore_home"
    restore_home.mkdir()
    monkeypatch.setenv("HOME", str(restore_home))

    fake = _FakeClient()
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake, object()))

    result = _runner.invoke(app, ["restore", str(dest), "--force", "--reindex"])
    assert result.exit_code == 0, result.output
    assert fake.reindexed == ["handbook"]
    assert "reindex handbook: ok" in result.output


def test_restore_refuses_nonempty_vault_without_force(tmp_path, monkeypatch):
    """Restore must not silently overwrite a populated vault."""
    src_home = tmp_path / "src_home"
    dest = tmp_path / "backup.tar.gz"
    monkeypatch.setenv("HOME", str(src_home))
    _populate_vault(src_home)
    assert _runner.invoke(app, ["backup", str(dest)]).exit_code == 0

    # Restore back over the SAME (non-empty) vault without --force.
    result = _runner.invoke(app, ["restore", str(dest)], input="n\n")
    assert result.exit_code != 0


def test_restore_corrupt_archive_gives_clean_error_and_preserves_vault(tmp_path, monkeypatch):
    """Restoring a corrupt/unsafe archive must raise a clean BackupError (no
    traceback) and leave the live vault completely intact.

    We craft a tar.gz that contains a valid ``coffer.db`` (so ``verify_backup``
    passes) plus a member with an absolute path that triggers
    ``tarfile.AbsolutePathError`` under ``filter="data"``.  The CLI must print
    a human-readable error and exit non-zero; the live vault DB must survive.
    """
    import io

    live_home = tmp_path / "live_home"
    monkeypatch.setenv("HOME", str(live_home))
    _populate_vault(live_home)
    live_db = live_home / ".coffer" / "coffer.db"
    assert live_db.exists()

    # Build a crafted archive: valid coffer.db + an absolute-path member.
    crafted = tmp_path / "crafted.tar.gz"
    with tarfile.open(crafted, "w:gz") as tar:
        # Valid coffer.db member — passes verify_backup.
        db_data = b"SQLite format 3\x00" + b"\x00" * 80
        db_info = tarfile.TarInfo(name="coffer.db")
        db_info.size = len(db_data)
        tar.addfile(db_info, io.BytesIO(db_data))

        # Symlink to an absolute path — triggers AbsoluteLinkError under
        # filter="data" (Python 3.12+), which is a tarfile.TarError subclass.
        evil_info = tarfile.TarInfo(name="evil_link")
        evil_info.type = tarfile.SYMTYPE
        evil_info.linkname = "/etc/malicious"
        tar.addfile(evil_info)

    result = _runner.invoke(app, ["restore", str(crafted), "--force"])

    # CLI must exit non-zero with a readable message — no Python traceback.
    assert result.exit_code != 0, f"expected non-zero exit, got 0; output: {result.output}"
    output_lower = result.output.lower()
    assert "traceback" not in output_lower, "traceback must not be shown to user"
    # The message should mention the archive problem.
    assert any(word in output_lower for word in ("corrupt", "unsafe", "invalid")), (
        f"expected error message mentioning corrupt/unsafe/invalid, got: {result.output}"
    )

    # The live vault DB is untouched.
    assert live_db.exists(), "live vault DB was destroyed by a failed restore"
