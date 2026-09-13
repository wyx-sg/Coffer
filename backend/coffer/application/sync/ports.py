"""Ports the sync application layer depends on; infrastructure implements them.

The git working tree is the one port big enough to live on its own; it is in
``git_port.py`` and re-exported here, so a caller still has one place to import
from.

Keeping these as protocols lets ``application/sync`` stay free of the
filesystem and sqlite (Contract 2b) while the composition root injects the
concrete adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from coffer.application.sync.git_port import GitMirrorPort
from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import ConvergeRun, PendingConfirmation
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.serialization import ResourceDoc


class ImportGate(Protocol):
    """Per-kind validation the importing machine runs BEFORE upserting a doc
    (spec vault-sync import reconciliation). Raise ``CofferError`` to report the doc
    as a per-resource failure — the rest of the bundle still imports, and the
    user can re-run the import once this machine satisfies the precondition
    (e.g. the agent's config dir exists here).

    ``scope`` is the doc's per-agent activation scope, passed so a scope-aware
    gate can let a doc that is dormant here through untouched instead of
    failing it on a machine-local precondition that does not apply."""

    kind: str

    async def validate(self, config: Mapping[str, object], *, scope: Any = None) -> None: ...


class PostImportHook(Protocol):
    """Per-kind side-effect reconciliation run AFTER an import (spec vault-sync
    import reconciliation). Re-applies machine-local side-effects (native
    config projections, on-disk transforms, deliveries) idempotently from the
    imported rows — current state, not deltas — and returns error strings,
    which are reported in the import summary."""

    kind: str

    async def reconcile(self) -> list[str]: ...


class SyncedStatePort(Protocol):
    """A module-owned shared-state area carried under ``state/<area>/``.

    Modules (channel pairing, memory store labels, ...) implement this and the
    composition root registers the providers — sync never imports kind modules
    (cross-kind fence). Docs are deterministic payloads: export writes the
    area, import upserts into local state."""

    @property
    def area(self) -> str:
        """Directory name under ``state/`` (kebab-case)."""
        ...

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        """Local state as (relative doc path without extension, payload) pairs.

        The second element is the path prefixes this machine owns. It is
        retained for provider compatibility and ignored by the exporter: a
        bundle is a snapshot of THIS machine, so every doc it returns is
        written and nothing else is preserved."""
        ...

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        """Apply the bundle's docs to local state; returns (doc path, error)
        pairs, which are reported as per-doc import failures."""
        ...

    async def delete_docs(self, rels: list[str]) -> None:
        """Remove local state for docs the vault no longer holds.

        New with bidirectional convergence: an area used to be import-only,
        because a one-way import was forbidden from deleting anything. A
        deletion only reaches here because some machine actually deleted the
        document relative to a shared base, so it is a decision, not an
        absence."""
        ...


class CredentialSyncPort(Protocol):
    """Ciphertext-only credential IO + locked-ref detection (never the key)."""

    def list_refs(self) -> list[str]: ...

    def read_ciphertext(self, ref: str) -> bytes | None: ...

    def write_ciphertext(self, ref: str, blob: bytes) -> None: ...

    def delete_ciphertext(self, ref: str) -> None:
        """Drop a credential the vault no longer holds. Never touches the key."""

    def locked_refs(self) -> list[str]:
        """Refs whose ciphertext cannot be decrypted on this machine (no/other key)."""


class MasterKeyPort(Protocol):
    """Out-of-band master-key transfer for the new-machine bootstrap."""

    def export_key(self) -> bytes | None: ...

    def install_key(self, key: bytes) -> None: ...


class BundlePort(Protocol):
    """Filesystem IO over one export bundle directory (spec vault-sync layout).

    Every method is synchronous blocking IO; the application layer runs them
    off the event loop.

    Every write is **differential** (spec vault-sync "Why deletion is safe"):
    a document is written only when its bytes changed and removed only when
    the vault no longer holds it, and no implementation may clear a directory
    and rewrite it. The bundle is the git working tree that gets
    three-way-merged, so a clear-and-rewrite would make "this vault never
    absorbed it" indistinguishable from "this vault deleted it".

    Held paths — the retry and not-applicable sets from
    ``ConvergenceStatePort`` — are configured on the implementation rather than
    passed per call, because they are one machine-wide fact every area obeys.
    No write may delete one."""

    def open_for_write(self) -> None:
        """Prepare the bundle directory for an export.

        It creates the directory and validates it. It MUST NOT clear anything:
        each area converges against local state in its own write method, which
        is what keeps the staged diff an honest account of what this vault
        changed."""

    def require_readable(self) -> None:
        """Raise ``SyncBundleInvalid`` unless the path is an existing bundle."""

    @property
    def path(self) -> str: ...

    def mirror_trees_out(self) -> None:
        """Copy the live knowledge/memory/skill trees into the bundle."""

    def mirror_trees_in(self) -> None:
        """Copy the bundle's trees back into the live vault (never deleting)."""

    def tree_counts(self) -> list[tuple[str, int]]:
        """(subdir, file count) for each mirrored tree present in the bundle,
        plus ``machines`` once the bundle carries a registry."""

    def write_manifest(self, manifest: Manifest) -> None: ...

    def read_manifest(self) -> Manifest | None: ...

    def write_resource_docs(
        self, docs: Sequence[Mapping[str, object]], *, unserializable: Sequence[str] = ()
    ) -> None:
        """Converge ``resources/`` on ``docs`` — one deterministic YAML file
        per doc, writing only what changed and removing only what ``docs`` no
        longer names (never a held path)."""

    def read_resource_docs(self) -> list[ResourceDoc]: ...

    def write_state_docs(self, area: str, docs: Sequence[tuple[str, Mapping[str, object]]]) -> None:
        """Converge ``state/<area>/`` on ``docs``, differentially and touching
        no other area."""

    def read_state_docs(self, area: str) -> list[tuple[str, dict[str, object]]]: ...

    def write_credential_blobs(self, blobs: Mapping[str, bytes]) -> None:
        """Converge ``credentials/`` on ``blobs`` — one ``<ref>.enc`` per
        ciphertext blob, differentially."""

    def read_credential_blobs(self) -> dict[str, bytes]: ...

    def write_machine_descriptor(
        self, machine_id: str, descriptor_doc: Mapping[str, object]
    ) -> None:
        """Write exactly ``machines/<machine_id>.yaml`` and no other machine's.

        Disjoint ownership is what makes the registry unable to conflict (spec
        vault-sync "The registry is a derived view, not a synced table"): two
        machines never stage the same path, so git merges descriptors trivially
        and the registry is whatever ``machines/*.yaml`` holds."""

    def read_machine_descriptors(self) -> dict[str, dict[str, Any]]:
        """Every descriptor in the bundle, keyed by machine id."""

    def delete_machine_descriptor(self, machine_id: str) -> None:
        """Retire a machine's descriptor.

        The one write to another machine's path, and it is deliberate: a
        machine that is gone cannot remove its own row, so retiring one is a
        human act performed from a machine that remains."""

    def list_files(self) -> list[str]:
        """All bundle-relative file paths (for the 'no key in the bundle' check)."""


class ConvergenceStatePort(Protocol):
    """This machine's local, never-synced convergence state (spec vault-sync).

    Three facts, and none of them travel:

    * the **pointer** — the commit this vault has provably absorbed. It is the
      base of every diff, and the only machine identity the algorithm needs.
    * the **retry set** — paths the working tree holds that this vault has not
      absorbed. The exporter must not delete them, or a failure to apply turns
      into a published deletion.
    * the **not-applicable set** — paths that cannot apply on this machine at
      all (an ``agent`` whose ``config_dir`` does not exist here). Preserved
      like a retry-set path but never retried and never reported as an error.
    """

    async def pointer(self) -> str | None: ...

    async def set_pointer(self, commit: str) -> None: ...

    async def clear_pointer(self) -> None:
        """Forget the base, so the next round joins instead of assuming one.

        Two callers, and both mean the same thing: this machine can no longer
        prove what it absorbed. The remote was cleared, or the commit the
        pointer names is gone from the working tree. Either way a base that
        cannot be verified is worse than no base — joining re-derives one from
        the remote's registry, while a stale base silently mis-frames every
        diff that follows."""

    async def clear_holds(self) -> None:
        """Drop every held path. A hold protects a path in one remote's tree;
        carrying it to a different remote protects nothing and hides a real
        deletion."""

    async def held_paths(self) -> tuple[set[str], set[str]]:
        """``(retry, not_applicable)`` — the paths the exporter must preserve."""

    async def hold(self, path: str, *, applicable: bool) -> None: ...

    async def release(self, path: str) -> None: ...

    async def pending(self) -> PendingConfirmation | None:
        """The round held at the deletion guard, if one is.

        Held state rather than a re-derived one: the round had already merged
        and possibly had an agent resolve conflicts by the time the guard
        tripped, and throwing that away to recompute it on confirmation would
        make the user's "yes" mean something slightly different from what they
        were shown."""

    async def set_pending(self, pending: PendingConfirmation | None) -> None: ...


class ConflictResolverPort(Protocol):
    """A bounded agentic pass over a conflicted working tree (spec vault-sync).

    It writes **only** into the working tree, never the live vault, and its
    output is not trusted: the caller runs a validation gate over every file it
    touched before treating the result as an ordinary merge. A resolver that is
    unavailable — no internal model configured — reports so rather than
    failing, because "stop and hand it to the user's own git" is the designed
    fallback, not an error path.
    """

    async def available(self) -> bool: ...

    async def resolve(self, paths: Sequence[str]) -> list[str]:
        """Attempt the conflicts; return the paths it believes it resolved."""


class VaultApplyPort(Protocol):
    """Applies one path's change to the live vault (spec vault-sync).

    One method per direction rather than a single "sync this path", because
    deletion is the operation that needed authorising and it should be visible
    at the seam. Raising ``CofferError`` reports the path as a per-path failure
    and never aborts the round.
    """

    #: Bundle path prefix this applier owns (``knowledge/``, ``resources/``, …).
    prefix: str

    async def upsert(self, path: str) -> None:
        """Apply the working tree's version of ``path`` to the vault."""

    async def remove(self, path: str) -> None:
        """Remove from the vault what ``path`` used to carry."""


class SyncRemoteRepoPort(Protocol):
    """Storage for the single sync remote and the last round's outcome.

    A port rather than the concrete repository so the application layer keeps
    no infrastructure import; the composition root injects the SQLAlchemy one.
    """

    async def get(self) -> BackupRemote | None: ...

    async def set(self, remote: BackupRemote) -> None: ...

    async def clear(self) -> None: ...

    async def record_run(self, run: ConvergeRun) -> None: ...

    async def last_run(self) -> ConvergeRun | None: ...


__all__ = [
    "BundlePort",
    "ConflictResolverPort",
    "ConvergenceStatePort",
    "CredentialSyncPort",
    "GitMirrorPort",
    "ImportGate",
    "MasterKeyPort",
    "PostImportHook",
    "SyncRemoteRepoPort",
    "SyncedStatePort",
    "VaultApplyPort",
]
