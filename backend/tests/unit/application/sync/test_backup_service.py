"""One backup run, in every outcome it has (spec vault-export-import ``## Backup``).

Everything here is a fake: the point of these tests is the *decisions* the
service makes — commit or not, push or not, what it records — and a real git
tree or database would only slow down the one thing worth asserting. The git
adapter's own behaviour is covered against a real repository in
``tests/integration/sync/test_git_mirror.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.sync.backup_service import BackupService
from coffer.domain.audit import AuditEntry, AuditEventType
from coffer.domain.sync.backup import BackupRemote, BackupRun, BackupRunStatus
from coffer.domain.sync.errors import BackupRemoteInvalid
from coffer.domain.sync.models import AreaCount, ExportSummary, ImportSummary
from coffer.infrastructure.sync.git_mirror import GitMirrorError

_WORKTREE = "~/.coffer/backup-under-test"
_EXPANDED = str(Path(_WORKTREE).expanduser())
_TOKEN_REF = "sync.BACKUP_TOKEN"
_TOKEN = "sup3rsecret"
_HEAD = "0ff1ce0"


class _FakeMirror:
    """Records every port call, so a test can assert what git was asked to do."""

    def __init__(
        self,
        *,
        staged: bool = False,
        unpushed: bool = False,
        push_error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._staged = staged
        # What a staged export touched. The default stands for a real change;
        # a test that wants "only the manifest was restamped" sets it.
        self.staged_files: list[str] = ["resources/mcp_server/thing.yaml"]
        self._unpushed = unpushed
        self._push_error = push_error
        self._head: str | None = _HEAD
        self.sha = "c0ffee1"

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def payload(self, name: str) -> dict[str, Any]:
        return next(kwargs for called, kwargs in self.calls if called == name)

    async def ensure_repo(self, *, remote_url: str, branch: str) -> None:
        self.calls.append(("ensure_repo", {"remote_url": remote_url, "branch": branch}))

    async def stage_all(self) -> bool:
        self.calls.append(("stage_all", {}))
        return self._staged

    async def staged_paths(self) -> list[str]:
        self.calls.append(("staged_paths", {}))
        return list(self.staged_files)

    async def discard_staged(self) -> None:
        self.calls.append(("discard_staged", {}))

    async def commit(self, message: str) -> str:
        self.calls.append(("commit", {"message": message}))
        return self.sha

    async def push(self, *, branch: str, token: str | None) -> None:
        self.calls.append(("push", {"branch": branch, "token": token}))
        if self._push_error is not None:
            raise self._push_error

    async def clone(self, *, remote_url: str, branch: str, token: str | None) -> None:
        self.calls.append(("clone", {"remote_url": remote_url, "branch": branch, "token": token}))

    async def fetch(self, *, token: str | None) -> None:
        self.calls.append(("fetch", {"token": token}))

    async def resolve_revision(self, revision: str) -> str:
        self.calls.append(("resolve_revision", {"revision": revision}))
        return "abcdef0"

    async def checkout(self, revision: str) -> None:
        self.calls.append(("checkout", {"revision": revision}))

    async def checkout_branch(self, branch: str) -> None:
        self.calls.append(("checkout_branch", {"branch": branch}))

    async def head(self) -> str | None:
        self.calls.append(("head", {}))
        return self._head

    async def has_unpushed(self, *, branch: str) -> bool:
        self.calls.append(("has_unpushed", {"branch": branch}))
        return self._unpushed


class _FakeSync:
    """``SyncService``'s two bundle methods, recording what they were asked for."""

    def __init__(self) -> None:
        self.exports: list[tuple[str, bool]] = []
        self.imports: list[str] = []

    async def export_bundle(self, path: str, *, with_credentials: bool = False) -> ExportSummary:
        self.exports.append((path, with_credentials))
        return ExportSummary(
            path=path,
            areas=[AreaCount(area="knowledge", count=12), AreaCount(area="skills", count=3)],
            credentials_included=with_credentials,
        )

    async def import_bundle(self, path: str) -> ImportSummary:
        self.imports.append(path)
        return ImportSummary(path=path)


class _FakeRemotes:
    """In-memory stand-in for ``SqlAlchemySyncRemoteRepo``."""

    def __init__(self, remote: BackupRemote | None = None) -> None:
        self.remote = remote
        self.runs: list[BackupRun] = []

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


class _FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def query(self, **_kwargs: Any) -> list[AuditEntry]:
        return list(self.entries)


class _FakeStore:
    """Credential store that records which refs were actually asked for."""

    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets
        self.reads: list[str] = []

    def get(self, ref: str) -> str | None:
        self.reads.append(ref)
        return self.secrets.get(ref)


@dataclass
class _Rig:
    service: BackupService
    mirror: _FakeMirror
    sync: _FakeSync = field(default_factory=_FakeSync)
    remotes: _FakeRemotes = field(default_factory=_FakeRemotes)
    audit: _FakeAuditRepo = field(default_factory=_FakeAuditRepo)
    store: _FakeStore = field(default_factory=lambda: _FakeStore({}))


def _remote(**overrides: Any) -> BackupRemote:
    fields: dict[str, Any] = {
        "url": "https://example.invalid/vault.git",
        "branch": "main",
        "worktree_path": _WORKTREE,
    }
    fields.update(overrides)
    return BackupRemote(**fields)


def _rig(
    *,
    remote: BackupRemote | None = None,
    staged: bool = False,
    unpushed: bool = False,
    push_error: Exception | None = None,
) -> _Rig:
    mirror = _FakeMirror(staged=staged, unpushed=unpushed, push_error=push_error)
    sync = _FakeSync()
    remotes = _FakeRemotes(remote)
    audit_repo = _FakeAuditRepo()
    store = _FakeStore({_TOKEN_REF: _TOKEN})
    service = BackupService(
        remotes=remotes,
        sync=sync,  # type: ignore[arg-type]
        mirror_factory=lambda _path: mirror,  # type: ignore[arg-type,return-value]
        credentials=CredentialResolver(store),
        audit=AuditService(audit_repo),  # type: ignore[arg-type]
    )
    return _Rig(
        service=service,
        mirror=mirror,
        sync=sync,
        remotes=remotes,
        audit=audit_repo,
        store=store,
    )


async def test_no_remote_configured_touches_nothing() -> None:
    rig = _rig(remote=None)

    run = await rig.service.run_once()

    assert run.status is BackupRunStatus.NO_CHANGE
    assert rig.mirror.calls == []
    assert rig.sync.exports == []
    assert rig.audit.entries == []


async def test_a_disabled_remote_touches_nothing() -> None:
    rig = _rig(remote=_remote(enabled=False))

    run = await rig.service.run_once()

    assert run.status is BackupRunStatus.NO_CHANGE
    assert rig.mirror.calls == []
    assert rig.sync.exports == []


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="an unchanged vault makes no backup commit",
)
async def test_an_unchanged_export_makes_no_commit() -> None:
    rig = _rig(remote=_remote(), staged=False, unpushed=False)

    run = await rig.service.run_once()

    assert rig.sync.exports == [(_EXPANDED, False)]
    assert "commit" not in rig.mirror.names
    assert "push" not in rig.mirror.names
    assert run.status is BackupRunStatus.NO_CHANGE
    assert run.commit is None
    assert rig.remotes.runs == [run]


async def test_a_restamped_manifest_alone_is_not_a_change() -> None:
    """Every export rewrites manifest.json's creation time, so a diff that
    touches nothing else means the vault stood still. Committing it would put
    an entry in the history for every tick — see the integration test that
    proves this against real git."""
    rig = _rig(remote=_remote(), staged=True, unpushed=False)
    rig.mirror.staged_files = ["manifest.json"]

    run = await rig.service.run_once()

    assert "commit" not in rig.mirror.names
    assert "push" not in rig.mirror.names
    # And nothing is left staged: a dirty index would make git refuse the
    # checkout that restore-from-history depends on.
    assert "discard_staged" in rig.mirror.names
    assert run.status is BackupRunStatus.NO_CHANGE


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="a changed vault is committed and pushed",
)
async def test_a_changed_export_is_committed_then_pushed() -> None:
    rig = _rig(remote=_remote(credential_ref=_TOKEN_REF), staged=True)

    run = await rig.service.run_once()

    assert rig.mirror.names.index("commit") < rig.mirror.names.index("push")
    # The message names the counts per area, so the history reads in vault
    # terms rather than as a wall of timestamps.
    assert rig.mirror.payload("commit")["message"] == "coffer backup: knowledge=12 skills=3"
    assert rig.mirror.payload("push")["branch"] == "main"
    assert run.status is BackupRunStatus.OK
    assert run.commit == rig.mirror.sha
    assert rig.remotes.runs == [run]
    (entry,) = rig.audit.entries
    assert entry.event_type == AuditEventType.VAULT_BACKED_UP.value
    assert entry.details == {"status": "ok", "commit": rig.mirror.sha}
    assert _TOKEN not in str(entry.details)


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="a failed push keeps the commit",
)
async def test_a_failed_push_keeps_the_commit_and_escapes_nothing() -> None:
    rejected = GitMirrorError(f"git push failed: could not read Password for https://{_TOKEN}@h")
    rig = _rig(remote=_remote(credential_ref=_TOKEN_REF), staged=True, push_error=rejected)

    run = await rig.service.run_once()

    assert run.status is BackupRunStatus.PUSH_FAILED
    # The commit stays: it is the only copy of this change while the remote is
    # unreachable, and the next run carries it out.
    assert rig.mirror.names.count("commit") == 1
    assert run.commit == rig.mirror.sha
    assert run.error is not None
    assert _TOKEN not in run.error
    assert "***" in run.error
    assert rig.remotes.runs == [run]
    (entry,) = rig.audit.entries
    assert entry.details == {"status": "push_failed", "commit": rig.mirror.sha}


async def test_an_outstanding_commit_is_pushed_without_a_second_commit() -> None:
    rig = _rig(remote=_remote(), staged=False, unpushed=True)

    run = await rig.service.run_once()

    assert "commit" not in rig.mirror.names
    assert "push" in rig.mirror.names
    assert run.status is BackupRunStatus.OK
    assert run.commit == _HEAD


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="credentials ride along only when the remote says so",
)
@pytest.mark.parametrize("opted_in", [True, False])
async def test_the_credential_opt_in_reaches_the_exporter(opted_in: bool) -> None:
    rig = _rig(remote=_remote(include_credentials=opted_in), staged=True)

    await rig.service.run_once()

    assert rig.sync.exports == [(_EXPANDED, opted_in)]


@pytest.mark.parametrize(
    ("credential_ref", "expected_token", "expected_reads"),
    [(_TOKEN_REF, _TOKEN, [_TOKEN_REF]), (None, None, [])],
)
async def test_the_token_is_resolved_only_when_a_ref_is_configured(
    credential_ref: str | None,
    expected_token: str | None,
    expected_reads: list[str],
) -> None:
    rig = _rig(remote=_remote(credential_ref=credential_ref), staged=True)

    await rig.service.run_once()

    assert rig.mirror.payload("push")["token"] == expected_token
    assert rig.store.reads == expected_reads


async def test_an_export_failure_is_reported_rather_than_raised() -> None:
    rig = _rig(remote=_remote())

    async def _boom(_path: str, *, with_credentials: bool = False) -> ExportSummary:
        raise GitMirrorError("git init failed: permission denied")

    rig.sync.export_bundle = _boom  # type: ignore[method-assign]

    run = await rig.service.run_once()

    assert run.status is BackupRunStatus.EXPORT_FAILED
    assert "commit" not in rig.mirror.names
    assert rig.remotes.runs == [run]


async def test_configure_get_clear_and_status_round_trip() -> None:
    rig = _rig(remote=None)
    assert await rig.service.get() is None
    assert await rig.service.status() == (None, None)

    await rig.service.configure(_remote(branch="backup"))
    remote = await rig.service.get()
    assert remote is not None
    assert remote.branch == "backup"
    assert await rig.service.status() == (remote, None)

    await rig.service.clear()
    assert await rig.service.get() is None


async def test_restore_returns_to_the_branch_even_when_the_import_fails() -> None:
    rig = _rig(remote=_remote())

    async def _boom(_path: str) -> ImportSummary:
        raise RuntimeError("bundle is mid-write")

    rig.sync.import_bundle = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await rig.service.restore(at="2026-09-09")

    assert rig.mirror.names[-1] == "checkout_branch"
    assert rig.mirror.payload("resolve_revision")["revision"] == "2026-09-09"


async def test_restore_clones_when_there_is_no_working_tree() -> None:
    rig = _rig(remote=None)
    rig.mirror._head = None

    summary = await rig.service.restore(from_url="https://example.invalid/vault.git")

    assert "clone" in rig.mirror.names
    assert "ensure_repo" not in rig.mirror.names
    assert rig.sync.imports == [str(Path("~/.coffer/sync").expanduser())]
    assert summary.path == str(Path("~/.coffer/sync").expanduser())


async def test_a_restore_with_no_remote_configured_uses_no_token() -> None:
    """The stored credential belongs to the stored remote.

    With nothing configured there is no credential to offer, and the url the
    user named must not be able to collect one. This is the belt to the
    refusal's braces: even if the two urls could ever coexist, the token is
    scoped to the url it was stored for.
    """
    rig = _rig(remote=None)

    await rig.service.restore(from_url="https://elsewhere.invalid/other.git")

    assert rig.store.reads == []
    assert rig.mirror.payload("fetch")["token"] is None


async def test_a_restore_from_the_configured_url_still_authenticates() -> None:
    rig = _rig(remote=_remote(credential_ref=_TOKEN_REF))

    await rig.service.restore(from_url="https://example.invalid/vault.git")

    assert rig.mirror.payload("fetch")["token"] == _TOKEN


async def test_restoring_another_repository_over_a_configured_one_is_refused() -> None:
    """The working tree belongs to the configured remote.

    Pulling an unrelated history into it would leave the next backup run unable
    to diff or fast-forward, so the backup stays broken until someone empties
    the tree by hand. Better to say so than to half-do it.
    """
    rig = _rig(remote=_remote())

    with pytest.raises(BackupRemoteInvalid):
        await rig.service.restore(from_url="https://elsewhere.invalid/other.git")

    assert rig.mirror.names == []
