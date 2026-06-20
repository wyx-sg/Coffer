"""Integration tests for BackupWorker.

Tests inject a fake or real create_backup callable and invoke _run_once()
directly to avoid running the infinite loop. The asyncio_mode = "auto"
config in pyproject.toml makes all async test functions run automatically.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from coffer.application.backup_worker import BackupWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _real_create_backup(dest: Path, *, include_master_key: bool = False) -> None:
    """Minimal real backup: writes a valid tar.gz containing a sentinel file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        # Add a tiny dummy member so the archive is non-empty and valid.
        import io

        data = b"sentinel"
        info = tarfile.TarInfo(name="coffer.db")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def _make_worker(
    backup_dir: Path,
    *,
    create_backup=_real_create_backup,
    keep: int = 3,
    interval_seconds: float = 3600,
) -> BackupWorker:
    return BackupWorker(
        create_backup=create_backup,
        backup_dir=backup_dir,
        keep=keep,
        interval_seconds=interval_seconds,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_run_once_creates_snapshot(tmp_path: Path) -> None:
    """A single _run_once() call writes one auto-coffer-<ts>.tar.gz file."""
    backup_dir = tmp_path / "backups"
    worker = _make_worker(backup_dir)

    await worker._run_once()

    files = list(backup_dir.glob("auto-coffer-*.tar.gz"))
    assert len(files) == 1, f"expected 1 backup file, got {files}"


async def test_run_once_filename_has_utc_timestamp(tmp_path: Path) -> None:
    """The created file matches the auto-coffer-YYYYmmddTHHMMSS.tar.gz pattern."""
    import re

    backup_dir = tmp_path / "backups"
    worker = _make_worker(backup_dir)

    await worker._run_once()

    files = list(backup_dir.glob("auto-coffer-*.tar.gz"))
    assert len(files) == 1
    pattern = re.compile(r"auto-coffer-\d{8}T\d{6}\.tar\.gz")
    assert pattern.match(files[0].name), f"unexpected filename: {files[0].name}"


async def test_rolling_retention_prunes_via_run_once(tmp_path: Path) -> None:
    """_run_once() prunes old auto-snapshots so only `keep` remain.

    Pre-populate backup_dir with (keep + 2) existing auto-snapshots at distinct
    mtimes, then call _run_once() once (which creates 1 new file and prunes).
    The result must be exactly `keep` auto-snapshot files — the oldest
    pre-existing ones are deleted.
    """
    import os

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    keep = 3
    pre_existing = keep + 2  # 5 old files before the new snapshot

    # Create files with distinct, old mtimes so they sort before the new snapshot.
    for i in range(pre_existing):
        f = backup_dir / f"auto-coffer-20000101T00000{i}.tar.gz"
        f.touch()
        mtime = 1_000_000 + i * 10  # epoch seconds far in the past
        os.utime(f, (mtime, mtime))

    worker = _make_worker(backup_dir, keep=keep)
    await worker._run_once()  # writes 1 new file, then prunes

    remaining = list(backup_dir.glob("auto-coffer-*.tar.gz"))
    assert len(remaining) == keep, (
        f"expected {keep} files after pruning, got {len(remaining)}: {remaining}"
    )


async def test_rolling_retention_keeps_newest_deterministic(tmp_path: Path) -> None:
    """Retention prunes oldest auto-snapshots by mtime, keeping the keep newest."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    keep = 2

    # Pre-populate backup_dir with 4 auto-snapshot files having distinct mtimes.
    old_files = []
    for i in range(4):
        f = backup_dir / f"auto-coffer-200001010000{i:02d}.tar.gz"
        f.touch()
        # Set progressively newer mtimes.
        mtime = 1000000 + i * 10
        import os

        os.utime(f, (mtime, mtime))
        old_files.append((mtime, f))

    worker = _make_worker(backup_dir, keep=keep)
    # _prune() is called inside _run_once(); trigger it by calling directly.
    worker._prune()

    remaining = sorted(
        backup_dir.glob("auto-coffer-*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
    )
    assert len(remaining) == keep
    # The 2 newest should survive.
    surviving_names = {p.name for p in remaining}
    expected_names = {old_files[-1][1].name, old_files[-2][1].name}
    assert surviving_names == expected_names


async def test_worker_does_not_prune_manual_backups(tmp_path: Path) -> None:
    """The worker's _prune() must NEVER delete manual coffer-*.tar.gz backups.

    Manual backups written by ``POST /vault/backup`` or ``coffer backup`` CLI
    use the ``coffer-<ts>.tar.gz`` naming convention.  The worker uses the
    distinct ``auto-coffer-<ts>.tar.gz`` prefix and must only glob that prefix,
    leaving any sibling manual backups untouched even when over the keep limit.
    """
    import os

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    keep = 1

    # Place auto-snapshots (will be pruned down to `keep`).
    for i in range(3):
        f = backup_dir / f"auto-coffer-20000101T00000{i}.tar.gz"
        f.touch()
        mtime = 1_000_000 + i * 10
        os.utime(f, (mtime, mtime))

    # Place a manual backup that must survive pruning regardless.
    manual = backup_dir / "coffer-manual.tar.gz"
    manual.touch()
    os.utime(manual, (500_000, 500_000))  # oldest mtime of all

    worker = _make_worker(backup_dir, keep=keep)
    worker._prune()

    # Only `keep` auto-snapshots remain.
    auto_remaining = list(backup_dir.glob("auto-coffer-*.tar.gz"))
    assert len(auto_remaining) == keep

    # The manual backup is untouched.
    assert manual.exists(), "worker must not delete manual coffer-*.tar.gz backups"


async def test_failing_create_backup_does_not_raise(tmp_path: Path) -> None:
    """A backup function that raises must be swallowed; _run_once() never raises."""
    backup_dir = tmp_path / "backups"

    def _boom(dest: Path, *, include_master_key: bool = False) -> None:
        raise RuntimeError("disk full")

    worker = _make_worker(backup_dir, create_backup=_boom)

    # Must not raise.
    await worker._run_once()

    # No files should have been created.
    assert not list(backup_dir.glob("*.tar.gz"))


async def test_stop_exits_run_loop(tmp_path: Path) -> None:
    """stop() causes run() to return promptly (within one interval)."""
    import asyncio

    backup_dir = tmp_path / "backups"
    worker = _make_worker(backup_dir, interval_seconds=3600)

    task = asyncio.create_task(worker.run())
    # Let the first _run_once() complete, then stop.
    await asyncio.sleep(0.05)
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()


# ---------------------------------------------------------------------------
# Regression: start_backup_worker enabled-path must not NameError (F821 guard)
# ---------------------------------------------------------------------------


async def test_start_backup_worker_enabled_path_no_nameerror(tmp_path: Path, monkeypatch) -> None:
    """start_backup_worker(app) with COFFER_AUTO_BACKUP_ENABLED=1 must not raise.

    This test specifically guards against the F821 regression where BackupWorker
    was used in app.py without being imported.  If the import inside
    backup_wiring.start_backup_worker is missing, this test raises NameError.
    """
    import asyncio
    import types

    monkeypatch.setenv("COFFER_AUTO_BACKUP_ENABLED", "1")
    monkeypatch.setenv("COFFER_AUTO_BACKUP_INTERVAL_HOURS", "24")
    monkeypatch.setenv("COFFER_AUTO_BACKUP_KEEP", "7")
    # Point vault_root() at tmp_path so backup_wiring never touches HOME.
    monkeypatch.setenv("HOME", str(tmp_path))

    # Minimal fake app with a state namespace, mirroring how other tests do it.
    app = types.SimpleNamespace(state=types.SimpleNamespace())

    from coffer.surfaces.http.backup_wiring import start_backup_worker, stop_backup_worker

    # Must not raise (NameError, ImportError, or anything else).
    start_backup_worker(app)  # type: ignore[arg-type]

    assert app.state.backup_worker is not None, "backup_worker should be set when enabled"
    assert app.state.backup_worker_task is not None, "backup_worker_task should be set when enabled"

    # Clean up: stop the worker and cancel the task so asyncio doesn't warn.
    await stop_backup_worker(app)  # type: ignore[arg-type]
    task = app.state.backup_worker_task
    if task is not None and not task.done():
        task.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await task
