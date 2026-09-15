"""A two-machine convergence harness (spec vault-sync ``## The converge round``).

Two independent vaults — each with its own SQLite database, knowledge tree,
skill store, credential store, master key, working tree, convergence state and
**injected** machine id — meet through one real bare git repository on disk.
Nothing here is faked below the git binary: the mirror shells out to real
``git``, the appliers write real files and real rows, and the round is the
production :class:`ConvergeRound` built from the production classes.

That is the point. The order of the round's seven steps is the whole safety
argument of the spec, and the only way a regression in it can be caught is by
running two vaults against a remote and watching what each one ends up
holding. A fake mirror would only assert our own beliefs about git's
three-way merge, which is exactly the thing under test.

The composition is done here rather than imported from
``surfaces/http/sync_wiring.py`` deliberately: the wiring is a composition
root that changes with the surfaces, and the algorithm's guarantees must not
be hostage to it.

Nothing in this module may reach the developer's real ``~/.coffer``: every
root is handed in, and the machine id is injected rather than derived from
this host.
"""

from __future__ import annotations

import asyncio
import hashlib
import pathlib
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.application.sync.appliers import (
    CredentialApplier,
    ResourceApplier,
    StateApplier,
    TreeApplier,
)
from coffer.application.sync.conflicts import ConflictArbiter
from coffer.application.sync.convergence import ConvergeRound
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.joining import JoinResolver
from coffer.application.sync.machines import MachineRegistry
from coffer.application.sync.service import ConvergeService
from coffer.domain.error_base import CofferError
from coffer.domain.resource import Kind, ResourceRef
from coffer.domain.scope import Scope
from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import ConvergeRun, PendingConfirmation
from coffer.domain.sync.diff import DeletionGuard
from coffer.domain.sync.models import ExportSummary
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_mirror import GitMirror

BRANCH = "main"
SNAPSHOT_PREFIX = "coffer/pre-apply/"


# --- kinds -----------------------------------------------------------------


class SyncableConfig(BaseModel):
    """A permissive config schema: these tests are about convergence, not
    about any one kind's validation rules."""

    model_config = ConfigDict(extra="allow")

    value: str = ""
    config_dir: str = ""
    credential_ref: str = ""


def _cited_credentials(config: dict[str, Any]) -> dict[str, str]:
    ref = config.get("credential_ref")
    return {"token": ref} if isinstance(ref, str) and ref else {}


def vault_kinds() -> dict[str, Kind]:
    """The kinds a converging vault carries, minimally but genuinely defined.

    ``mcp_server`` supports scope — reach is tested through it — and cites a
    credential, so deleting one exercises the orphaned-credential release that
    seeded the 2026-07-10 incident.

    ``channel`` is here because it is the kind whose travel is the interesting
    case: it used to be withheld from the bundle entirely, and it now converges
    like everything else, carrying inside its config the one machine whose
    daemon runs its adapter. Testing that it travels — and that its binding
    survives the trip untouched — needs a real row and a real document.
    """
    return {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP server",
            config_schema=SyncableConfig,
            supports_scope=True,
            credential_ref_extractor=_cited_credentials,
        ),
        "skill": Kind(
            name="skill",
            display_name="Skill",
            config_schema=SyncableConfig,
            supports_scope=True,
        ),
        "agent": Kind(name="agent", display_name="Agent", config_schema=SyncableConfig),
        "channel": Kind(
            name="channel",
            display_name="Channel",
            config_schema=SyncableConfig,
            credential_ref_extractor=_cited_credentials,
        ),
    }


# --- test doubles that stand in for things outside this slice ---------------


class GateRefusedError(CofferError):
    """An import gate refusing a document that could apply here later."""

    code = "SYNC_GATE_REFUSED"


class GateNotApplicableError(CofferError):
    """An import gate refusing a document that can never apply here."""

    code = "KIND_NOT_APPLICABLE"


class RecordingGate:
    """An ``ImportGate`` that records what it saw and can be told to refuse.

    Refusal keys off a marker in the document's config rather than its name,
    because the port hands the gate a config and nothing else — reach does not
    travel, so there is no scope for it to be handed.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.seen: list[dict[str, Any]] = []
        self.refuse_value: str | None = None
        self.refuse_permanently = False

    async def validate(self, config: Mapping[str, object]) -> None:
        self.seen.append(dict(config))
        if self.refuse_value is not None and config.get("value") == self.refuse_value:
            if self.refuse_permanently:
                raise GateNotApplicableError(f"{self.kind} cannot apply on this machine")
            raise GateRefusedError(f"{self.kind} cannot be applied here yet")


class RecordingHook:
    """A ``PostImportHook`` that counts its runs and can report a failure.

    Stands in for the real ones — the agent's native-config projection, the
    provider's, the skill deliveries — which reach outside the vault into
    machine-local files this slice deliberately knows nothing about. What the
    round owes them is a call after the apply and a place to put what went
    wrong, and that is what this asserts.
    """

    def __init__(self, kind: str = "agent") -> None:
        self.kind = kind
        self.runs = 0
        self.errors: list[str] = []
        self.raises: Exception | None = None

    async def reconcile(self) -> list[str]:
        self.runs += 1
        if self.raises is not None:
            raise self.raises
        return list(self.errors)


class ScriptedResolver:
    """A ``ConflictResolverPort`` whose output the test writes itself.

    A real agentic pass is non-deterministic and needs a model; what the round
    actually depends on is the *shape* of the contract — an unavailable
    resolver, a resolver that writes a good file, a resolver that claims a
    path it left a conflict marker in. All three are scripted here.
    """

    def __init__(self, worktree: pathlib.Path) -> None:
        self._worktree = worktree
        self.enabled = False
        #: bundle path -> bytes the resolver writes into the working tree.
        self.writes: dict[str, bytes] = {}
        #: Paths it claims to have resolved; defaults to the ones it wrote.
        self.claims: list[str] | None = None
        self.calls: list[list[str]] = []

    async def available(self) -> bool:
        return self.enabled

    async def resolve(self, paths: Sequence[str]) -> list[str]:
        self.calls.append(list(paths))
        written: list[str] = []
        for path in paths:
            payload = self.writes.get(path)
            if payload is None:
                continue
            target = self._worktree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            written.append(path)
        return list(self.claims) if self.claims is not None else written


class StubStateProvider:
    """A module-owned shared-state area (spec vault-sync "Shared state")."""

    area = "peers"

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, object]] = {}

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        return sorted(self.docs.items()), [""]

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        for rel, payload in docs:
            self.docs[rel] = dict(payload)
        return []

    async def delete_docs(self, rels: list[str]) -> None:
        for rel in rels:
            self.docs.pop(rel, None)


class NoKeyring:
    """The master key never falls back to a real keychain in a test."""

    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("keychain must not be used in tests")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        raise AssertionError("keychain must not be used in tests")


class ConvergenceState:
    """``ConvergenceStatePort`` over process memory.

    The three facts it holds are explicitly machine-local and never travel, so
    an in-memory implementation is the whole contract. ``forget()`` is what a
    reinstall does to them, which is the setup for the returning-machine
    scenarios.
    """

    def __init__(self) -> None:
        self._pointer: str | None = None
        self._retry: set[str] = set()
        self._not_applicable: set[str] = set()
        self._pending: PendingConfirmation | None = None

    async def pointer(self) -> str | None:
        return self._pointer

    async def clear_pointer(self) -> None:
        self._pointer = None

    async def clear_holds(self) -> None:
        self._retry.clear()
        self._not_applicable.clear()

    async def set_pointer(self, commit: str) -> None:
        self._pointer = commit

    async def held_paths(self) -> tuple[set[str], set[str]]:
        return set(self._retry), set(self._not_applicable)

    async def hold(self, path: str, *, applicable: bool) -> None:
        (self._retry if applicable else self._not_applicable).add(path)

    async def release(self, path: str) -> None:
        self._retry.discard(path)
        self._not_applicable.discard(path)

    async def pending(self) -> PendingConfirmation | None:
        return self._pending

    async def set_pending(self, pending: PendingConfirmation | None) -> None:
        self._pending = pending

    # --- test affordances ---------------------------------------------------

    def held_now(self) -> set[str]:
        """The bundle paths the exporter must preserve, read synchronously —
        the form ``Bundle`` wants, since its writes are blocking IO."""
        return self._retry | self._not_applicable

    def forget(self) -> None:
        """What a Coffer reinstall does: the pointer and the retry set are
        local state and go with ``~/.coffer``."""
        self._pointer = None
        self._retry.clear()
        self._not_applicable.clear()
        self._pending = None


def bare_remote(path: pathlib.Path) -> str:
    """A real bare repository to converge through, with an identity of its own
    so a machine with no global git config can still be committed against."""
    subprocess.run(
        ["git", "init", "--bare", "-b", BRANCH, str(path)], check=True, capture_output=True
    )
    for key, value in (("user.email", "harness@localhost"), ("user.name", "Harness")):
        subprocess.run(
            ["git", "-C", str(path), "config", key, value], check=True, capture_output=True
        )
    return str(path)


class VaultMachine:
    """One installation of Coffer, whole and self-contained."""

    def __init__(
        self,
        *,
        name: str,
        machine_id: str,
        root: pathlib.Path,
        remote_url: str,
        guard: DeletionGuard,
        with_credentials: bool,
        key_material: bytes | None = None,
    ) -> None:
        self.name = name
        self.machine_id = machine_id
        self.root = root
        self.remote_url = remote_url
        self.home = root
        self.knowledge_root = root / "knowledge"
        self.skills_root = root / "skills"
        self.worktree = root / "sync"
        self.db_path = root / "coffer.db"
        self.with_credentials = with_credentials
        self._guard = guard
        self._key_material = key_material
        self.state = ConvergenceState()
        self.state_provider = StubStateProvider()
        self.gate = RecordingGate("mcp_server")
        self.hook = RecordingHook("agent")
        self.resolver = ScriptedResolver(self.worktree)
        self.published_descriptor_commits: list[str] = []

    # --- construction -------------------------------------------------------

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.knowledge_root.mkdir(parents=True, exist_ok=True)
        self.skills_root.mkdir(parents=True, exist_ok=True)

        self.engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{self.db_path}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = session_maker(self.engine)
        self.sessions = sessions

        self.audit = AuditService(SqlAlchemyAuditRepo(sessions))
        self.master_key = MasterKeyManager(self.root / "master.key", NoKeyring())
        if self._key_material is not None:
            # The out-of-band bootstrap (``coffer sync key import``): the key
            # never travels inside the repository, so a machine that must read
            # another's ciphertext is given it before it ever converges.
            self.master_key.install_key(self._key_material)
        key = self.master_key.resolve(allow_create=True)
        assert key is not None
        self.credential_store = EncryptedCredentialStore(self.db_path, key)
        self.resources = ResourceService(
            kinds=vault_kinds(),
            repo=SqlAlchemyResourceRepo(sessions),
            audit=self.audit,
            credentials=self.credential_store,
        )
        self.credentials = CredentialSyncAdapter(self.db_path, self.master_key)

        self.bundle = Bundle(
            self.worktree,
            trees=[("knowledge", self.knowledge_root), ("skills", self.skills_root)],
            held_paths=self.state.held_now,
        )
        self.exporter = SyncExporter(
            self.resources,
            self.credentials,
            [self.state_provider],
            home=str(self.home),
        )
        self.mirror = GitMirror(self.worktree)
        self.registry = MachineRegistry(
            machine_id=self.machine_id,
            machine_name=self.name,
            derived=True,
            coffer_version="test",
            resources=self.resources,
            key_fingerprint=self.key_fingerprint(),
        )
        self.round = self._build_round()

    def _build_round(self) -> ConvergeRound:
        return ConvergeRound(
            mirror=self.mirror,
            state=self.state,
            appliers=[
                TreeApplier("knowledge/", worktree=self.worktree, live_root=self.knowledge_root),
                TreeApplier("skills/", worktree=self.worktree, live_root=self.skills_root),
                ResourceApplier(
                    self.resources,
                    worktree=self.worktree,
                    gates=[self.gate],
                    home=str(self.home),
                ),
                StateApplier([self.state_provider], worktree=self.worktree, home=str(self.home)),
                CredentialApplier(self.credentials, worktree=self.worktree),
            ],
            arbiter=ConflictArbiter(self.resolver),
            joining=JoinResolver(machine_id=self.machine_id, branch=BRANCH),
            serialize=self._serialize,
            guard=self._guard,
            branch=BRANCH,
            post_import=[self.hook],
        )

    async def close(self) -> None:
        await self.engine.dispose()

    def key_fingerprint(self) -> str | None:
        key = self.master_key.export_key()
        return hashlib.sha256(key).hexdigest()[:12] if key else None

    # --- the service the surfaces drive -------------------------------------

    def service(
        self, *, lock: asyncio.Lock | None = None, guard_worktree: bool = False
    ) -> ConvergeService:
        """The real :class:`ConvergeService` over this machine's graph.

        The surfaces (HTTP routes, CLI) talk to a service, never to a round, so
        testing them means building the real one. Its factories return this
        machine's own mirror, round and bundle rather than constructing new
        ones: the working tree is fixed for a machine in these tests, and
        handing back the same objects is what lets a test inspect the state a
        route just changed.

        ``guard_worktree`` hands the service this machine's roots as the
        protected ones, so a test can drive the working-tree containment check
        through a surface; off by default because the routes' fixtures store
        the spec's default ``~/.coffer/sync`` and never resolve it.
        """
        return ConvergeService(
            remotes=SqlAlchemySyncRemoteRepo(self.sessions),
            state=self.state,
            round_factory=lambda _mirror, _branch: self.round,
            mirror_factory=lambda _worktree: self.mirror,
            bundle_factory=lambda _worktree: self.bundle,
            set_machine_name=self._rename,
            credentials=CredentialResolver(self.credential_store),
            credential_store=self.credentials,
            master_key=self.master_key,
            audit=self.audit,
            lock=lock,
            protected_roots=[self.knowledge_root, self.skills_root] if guard_worktree else (),
            coffer_dir=self.root if guard_worktree else None,
        )

    def _rename(self, name: str) -> None:
        """Stand in for ``write_machine_name``, which writes daemon-config.json.

        A test must never touch this host's real ``~/.coffer``, so the persisted
        half of a rename is held in memory here. The half that matters to the
        fleet — the running registry taking the new label, so the next
        descriptor it publishes carries it — is the production
        ``MachineRegistry.rename`` that ``ConvergeService.rename_self`` calls.
        """
        self.name = name
        self.registry.rename(name)

    async def remote_config(self, *, enabled: bool = True) -> BackupRemote:
        """Store this machine's remote, as ``PUT /sync/remote`` would.

        Written straight through the repository rather than through
        ``set_remote``: the reachability probe that method performs is tested on
        its own, and a fixture that merely needs a configured remote should not
        depend on it.
        """
        remote = BackupRemote(
            url=self.remote_url,
            branch=BRANCH,
            include_credentials=self.with_credentials,
            enabled=enabled,
            worktree_path=str(self.worktree),
        )
        await SqlAlchemySyncRemoteRepo(self.sessions).set(remote)
        return remote

    # --- the round ----------------------------------------------------------

    async def _serialize(self) -> ExportSummary:
        """Step 1's callable: the vault into the tree, plus this machine's own
        descriptor — the one document a machine writes about itself and about
        no other (spec vault-sync "The registry is a derived view")."""
        summary = await self.exporter.export(self.bundle, with_credentials=self.with_credentials)
        pointer = await self.state.pointer()
        commit = pointer if pointer and pointer != GitMirror.EMPTY_TREE else None
        await self.registry.publish_self(self.bundle, commit=commit, today=date.today())
        return summary

    async def converge(
        self, *, join_choice: str | None = None, confirmed: PendingConfirmation | None = None
    ) -> ConvergeRun:
        """One round, exactly as ``ConvergeService`` drives it."""
        await self.mirror.ensure_repo(remote_url=self.remote_url, branch=BRANCH)
        run = await self.round.run(token=None, join_choice=join_choice, confirmed=confirmed)
        if run.commit:
            self.published_descriptor_commits.append(run.commit)
        return run

    async def confirm(self) -> ConvergeRun:
        """Accept a held round, as ``ConvergeService.confirm`` does: clear the
        hold and re-derive the round, waiving the guard for that hold's own
        direction and only while the remote still stands where it was raised."""
        pending = await self.state.pending()
        assert pending is not None, "nothing is held at the deletion guard"
        await self.state.set_pending(None)
        return await self.converge(confirmed=pending)

    async def rebuild(self) -> ConvergeRun:
        """Rebuild this machine from the remote, as ``ConvergeService.rebuild``
        does: take the remote's tip whole, discard what only this machine has,
        push nothing, and clear any hold."""
        await self.mirror.ensure_repo(remote_url=self.remote_url, branch=BRANCH)
        await self.mirror.fetch(token=None)
        tip = await self.mirror.resolve_revision(f"origin/{BRANCH}")
        run = await self.round.rebuild_to(tip)
        await self.state.set_pointer(tip)
        await self.state.set_pending(None)
        return run

    async def reject(self) -> None:
        """Discard a held round. The vault was never touched — the guard runs
        before the apply — so this only has to undo the tree."""
        pending = await self.state.pending()
        assert pending is not None, "nothing is held at the deletion guard"
        pointer = await self.state.pointer()
        if pointer:
            await self.mirror.reset_hard(pointer)
        await self.state.set_pending(None)

    async def rollback(self) -> ConvergeRun:
        """The most recent pre-apply snapshot, run backwards."""
        pointer = await self.state.pointer()
        assert pointer is not None
        snapshots = await self.mirror.tags(SNAPSHOT_PREFIX)
        assert snapshots, "no pre-apply snapshot to roll back to"
        target = await self.mirror.resolve_revision(snapshots[0])
        # The pointer stays put, as ``ConvergeService.rollback`` leaves it:
        # moving it back to the snapshot would make the next round re-derive
        # the very diff the rollback undid.
        return await self.round.reverse_to(pointer, target)

    async def restore(self, revision: str) -> ConvergeRun:
        """``coffer sync restore --at <rev>``, as ``ConvergeService`` drives it.

        Deletions are dropped and the pointer does not move: a restore brings
        back what history holds without discarding what the vault has gained
        since, and it has not un-absorbed anything.
        """
        pointer = await self.state.pointer()
        assert pointer is not None
        target = await self.mirror.resolve_revision(revision)
        return await self.round.reverse_to(pointer, target, delete=False)

    # --- vault edits --------------------------------------------------------

    def write_knowledge(self, collection: str, name: str, body: str) -> pathlib.Path:
        path = self.knowledge_root / collection / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def read_knowledge(self, collection: str, name: str) -> str | None:
        path = self.knowledge_root / collection / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def delete_knowledge(self, collection: str, name: str) -> None:
        (self.knowledge_root / collection / f"{name}.md").unlink()

    def knowledge_paths(self) -> set[str]:
        return {
            p.relative_to(self.knowledge_root).as_posix()
            for p in self.knowledge_root.rglob("*")
            if p.is_file()
        }

    def write_skill(self, name: str, body: str = "# skill\n") -> pathlib.Path:
        path = self.skills_root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def has_skill_files(self, name: str) -> bool:
        return (self.skills_root / name / "SKILL.md").is_file()

    def delete_skill_files(self, name: str) -> None:
        shutil.rmtree(self.skills_root / name)

    async def register(
        self,
        kind: str,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        await self.resources.register(
            kind, name, config or {"value": name}, "test", allow_lifecycle_kind=True
        )

    async def edit_config(self, kind: str, name: str, config: dict[str, Any]) -> None:
        await self.resources.update_config(
            ResourceRef(kind, name), config, "test", allow_lifecycle_kind=True
        )

    async def delete_resource(self, kind: str, name: str) -> None:
        await self.resources.delete(ResourceRef(kind, name), "test")

    async def resource_names(self, kind: str) -> list[str]:
        return sorted(r.name for r in await self.resources.list(kind=kind))

    async def set_scope(self, kind: str, name: str, scope: Scope | None) -> None:
        await self.resources.update_scope(ResourceRef(kind, name), scope, actor="test")

    async def set_enabled(self, kind: str, name: str, enabled: bool) -> None:
        await self.resources.set_enabled(ResourceRef(kind, name), enabled, actor="test")

    async def reach(self, kind: str, name: str) -> tuple[bool, Scope | None]:
        """This machine's answer for a resource: is it live, and for whom.

        The two halves are one decision to the user and one assertion here —
        a test that checked only ``enabled`` would pass while the agent
        allow-list crossed a machine boundary behind it.
        """
        resource = await self.find(kind, name)
        assert resource is not None, f"{kind}/{name} is not registered on {self.name}"
        return resource.enabled, resource.scope

    async def find(self, kind: str, name: str) -> Any:
        from coffer.domain.errors import ResourceNotFound

        try:
            return await self.resources.get(ResourceRef(kind, name))
        except ResourceNotFound:
            return None

    def set_credential(self, ref: str, value: str) -> None:
        self.credential_store.set(ref, value)

    def has_credential(self, ref: str) -> bool:
        return self.credential_store.exists(ref)

    async def audit_events(self, event_type: str) -> int:
        return len(await self.audit.query(event_type=event_type, limit=500))

    # --- the working tree ---------------------------------------------------

    def tree_text(self, path: str) -> str | None:
        """One document as it sits in the git working tree, or None."""
        target = self.worktree / path
        return target.read_text(encoding="utf-8") if target.is_file() else None

    def tree_paths(self) -> set[str]:
        """Every file in the working tree, ``.git`` aside."""
        return {
            rel
            for rel in (
                p.relative_to(self.worktree).as_posix()
                for p in self.worktree.rglob("*")
                if p.is_file()
            )
            if not rel.startswith(".git/")
        }

    async def snapshots(self) -> list[str]:
        """The pre-apply snapshot tags, newest first."""
        return await self.mirror.tags(SNAPSHOT_PREFIX)

    async def machine_views(self) -> list[Any]:
        """The machines table as this machine renders it."""
        return await self.registry.list(self.bundle)

    # --- damage the tests inflict ------------------------------------------

    def forget_worktree(self) -> None:
        """What a reinstall does to ``~/.coffer/sync``: the working tree, its
        history and its remote-tracking refs all go. The vault's own files are
        somewhere else and survive."""
        shutil.rmtree(self.worktree, ignore_errors=True)

    async def wipe_vault(self) -> None:
        """What a reinstall that took ``~/.coffer`` with it leaves behind: the
        files are gone and the registry is empty, but the machine is the same
        machine."""
        shutil.rmtree(self.knowledge_root, ignore_errors=True)
        shutil.rmtree(self.skills_root, ignore_errors=True)
        self.knowledge_root.mkdir(parents=True, exist_ok=True)
        self.skills_root.mkdir(parents=True, exist_ok=True)
        for resource in await self.resources.list():
            await self.resources.delete(ResourceRef(resource.kind, resource.name), "test")

    # --- inspection ---------------------------------------------------------

    async def remote_paths(self) -> set[str]:
        """What the remote's branch tip holds, read through git itself."""
        out = subprocess.run(
            ["git", "-C", self.remote_url, "ls-tree", "-r", "--name-only", BRANCH],
            check=True,
            capture_output=True,
            text=True,
        )
        return {line for line in out.stdout.splitlines() if line}

    async def remote_text(self, path: str, *, revision: str = BRANCH) -> str | None:
        """One document as the remote holds it, read through git itself."""
        out = subprocess.run(
            ["git", "-C", self.remote_url, "show", f"{revision}:{path}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return out.stdout if out.returncode == 0 else None

    async def remote_commit_count(self) -> int:
        out = subprocess.run(
            ["git", "-C", self.remote_url, "rev-list", "--count", BRANCH],
            check=False,
            capture_output=True,
            text=True,
        )
        return int(out.stdout.strip() or "0")

    async def local_commit_count(self) -> int:
        out = subprocess.run(
            ["git", "-C", str(self.worktree), "rev-list", "--count", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        return int(out.stdout.strip() or "0")

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


async def build_machine(
    *,
    name: str,
    machine_id: str,
    root: pathlib.Path,
    remote_url: str,
    guard: DeletionGuard | None = None,
    with_credentials: bool = True,
    key_material: bytes | None = None,
) -> VaultMachine:
    """One machine, fully wired. ``machine_id`` is injected — a test must
    never read this host's real identifier."""
    machine = VaultMachine(
        name=name,
        machine_id=machine_id,
        root=root,
        remote_url=remote_url,
        guard=guard or DeletionGuard(),
        with_credentials=with_credentials,
        key_material=key_material,
    )
    await machine.start()
    return machine


#: Injected rather than derived. ``machine_id`` is normally read out of the
#: host, and a test that did that would be asserting something about the
#: developer's laptop; these are the two machines every scenario talks about.
MACHINE_A = "a1a1a1a1a1a1a1a1"
MACHINE_B = "b2b2b2b2b2b2b2b2"


async def two_machines(
    tmp_path: pathlib.Path,
    *,
    guard: DeletionGuard | None = None,
    with_credentials: bool = True,
    shared_key: bool = False,
) -> tuple[VaultMachine, VaultMachine]:
    """Two whole vaults and one real bare repository between them."""
    url = bare_remote(tmp_path / "remote.git")
    a = await build_machine(
        name="laptop",
        machine_id=MACHINE_A,
        root=tmp_path / "machine-a",
        remote_url=url,
        guard=guard,
        with_credentials=with_credentials,
    )
    b = await build_machine(
        name="desktop",
        machine_id=MACHINE_B,
        root=tmp_path / "machine-b",
        remote_url=url,
        guard=guard,
        with_credentials=with_credentials,
        # Two machines start with two different master keys, which is the
        # truthful default: a machine holding another's ciphertext without the
        # key reports those refs locked. ``shared_key`` is the bootstrap having
        # already happened.
        key_material=a.master_key.export_key() if shared_key else None,
    )
    return a, b


async def settle(*machines: VaultMachine) -> None:
    """Converge each machine until the fleet is quiet.

    Three rounds each, alternating, because convergence is genuinely a
    conversation: the first round of a joining machine publishes its documents
    but cannot yet name the commit it reached (its base was the empty tree), and
    the second is what writes that into its descriptor. A test that wants "two
    machines that already agree" as its *given* wants this, not a single round.
    """
    for _ in range(3):
        for machine in machines:
            await machine.converge()
