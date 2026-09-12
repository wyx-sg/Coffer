"""An idle vault must not put a commit in the backup history every tick.

Spec vault-export-import ``## Backup``. The unit tests for ``BackupService``
script ``stage_all()`` to return a chosen boolean, so they can say what the
service does with an answer but never whether the answer is right. This test
uses the **real** ``GitMirror`` against a real repository, and an export stub
that behaves the way the real exporter does — rewriting ``manifest.json`` with
a fresh creation time on every call, which the spec's own determinism scenario
allows ("byte-identical apart from the manifest's creation time").

Without change detection that looks past the manifest, an hourly backup writes
24 commits a day for a vault nobody touched, and `restore --at <date>` has to
see through all of them.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.sync.backup_service import BackupService
from coffer.domain.sync.backup import BackupRemote, BackupRun, BackupRunStatus
from coffer.domain.sync.models import ExportSummary
from coffer.infrastructure.sync.git_mirror import GitMirror


class _ExportStub:
    """Writes a bundle whose only per-call difference is the manifest's stamp."""

    def __init__(self) -> None:
        self.payload = "the vault's one file\n"
        self.calls: list[bool] = []

    async def export_bundle(self, path: str, *, with_credentials: bool = False) -> ExportSummary:
        self.calls.append(with_credentials)
        root = pathlib.Path(path)
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(
            json.dumps(
                {"schema_version": 1, "created_at": datetime.now(tz=UTC).isoformat()},
                indent=2,
            )
        )
        (root / "resources").mkdir(exist_ok=True)
        (root / "resources" / "thing.yaml").write_text(self.payload)
        return ExportSummary(path=path)


@dataclass
class _Remotes:
    remote: BackupRemote | None = None
    runs: list[BackupRun] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.runs = []

    async def get(self) -> BackupRemote | None:
        return self.remote

    async def set(self, remote: BackupRemote) -> None:
        self.remote = remote

    async def clear(self) -> None:
        self.remote = None

    async def record_run(self, run: BackupRun) -> None:
        self.runs.append(run)

    async def last_run(self) -> BackupRun | None:
        return self.runs[-1] if self.runs else None


class _AuditRepo:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def insert(self, event: Any) -> None:
        self.events.append(event)


class _Store:
    def get(self, ref: str) -> str | None:
        return None


def _commits(repo: pathlib.Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


@pytest.fixture
def rig(tmp_path: pathlib.Path):
    from coffer.application.audit_service import AuditService

    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    worktree = tmp_path / "worktree"
    export = _ExportStub()
    remotes = _Remotes(BackupRemote(url=str(bare), branch="main", worktree_path=str(worktree)))
    service = BackupService(
        remotes=remotes,  # type: ignore[arg-type]
        sync=export,  # type: ignore[arg-type]
        mirror_factory=lambda path: GitMirror(path),
        credentials=CredentialResolver(_Store()),
        audit=AuditService(_AuditRepo()),  # type: ignore[arg-type]
    )
    return service, export, worktree, bare


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="an unchanged vault makes no backup commit",
)
@pytest.mark.asyncio
async def test_a_second_run_on_an_idle_vault_adds_no_commit(rig) -> None:
    service, _export, worktree, _bare = rig

    first = await service.run_once()
    assert first.status is BackupRunStatus.OK
    assert len(_commits(worktree)) == 1

    second = await service.run_once()
    assert second.status is BackupRunStatus.NO_CHANGE
    assert len(_commits(worktree)) == 1, (
        "the manifest's creation time changed, but nothing in the vault did"
    )


@pytest.mark.asyncio
async def test_a_real_change_still_commits(rig) -> None:
    service, export, worktree, _bare = rig

    await service.run_once()
    export.payload = "the vault's one file, edited\n"
    run = await service.run_once()

    assert run.status is BackupRunStatus.OK
    assert len(_commits(worktree)) == 2


@pytest.mark.asyncio
async def test_the_idle_run_leaves_the_remote_where_it_was(rig) -> None:
    service, _export, _worktree, bare = rig

    await service.run_once()
    before = _commits(bare)
    await service.run_once()

    assert _commits(bare) == before


@pytest.mark.asyncio
async def test_an_idle_run_leaves_a_tree_a_restore_can_still_move(rig) -> None:
    """The recovery path has to survive the runs that happen most.

    An idle run stages the restamped manifest and then declines to commit it.
    If it left that staged, git would refuse the next checkout ("your local
    changes would be overwritten"), and `restore --at` — the whole reason the
    history exists — would fail on any vault that had been quiet for an hour.
    """
    service, export, worktree, _bare = rig

    await service.run_once()  # first real commit
    export.payload = "edited\n"
    await service.run_once()  # a second, so there is history to move back to
    await service.run_once()  # the idle run that stages only the manifest

    first = subprocess.run(
        ["git", "-C", str(worktree), "rev-list", "--max-parents=0", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    moved = subprocess.run(
        ["git", "-C", str(worktree), "checkout", "--detach", first],
        check=False,
        capture_output=True,
        text=True,
    )
    assert moved.returncode == 0, moved.stderr
