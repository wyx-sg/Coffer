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
from coffer.domain.sync.convergence import ConvergeRun, PendingConfirmation, RunRecord
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.serialization import ResourceDoc


class ImportGate(Protocol):
    """Per-kind validation this machine runs BEFORE upserting a doc (spec
    vault-sync ``## Applying a diff``). Raise ``CofferError`` to report the doc
    as a per-path failure — the rest of the round still applies, the path is
    held, and the next round retries it once this machine satisfies the
    precondition (e.g. the agent's config dir exists here).

    A gate sees the config and nothing else. It used to be handed the document's
    activation scope as well, so a scope-aware gate could wave a doc that was
    dormant here past a machine-local precondition — but reach no longer travels
    (spec vault-sync ``## What does not sync``), and a gate that wants that
    leniency now reads this machine's own row for it, which is the only place
    the answer was ever a fact about this machine."""

    kind: str

    async def validate(self, config: Mapping[str, object]) -> None: ...


class PostImportHook(Protocol):
    """Per-kind side-effect reconciliation run AFTER a round applies (spec
    vault-sync ``## Applying a diff``). Re-applies machine-local side-effects
    (native config projections, on-disk transforms, deliveries) idempotently
    from current state — not from the diff — and returns error strings, which
    the round reports among its failures."""

    kind: str

    async def reconcile(self) -> list[str]: ...


class SyncedStatePort(Protocol):
    """A module-owned shared-state area carried under ``state/<area>/``.

    Modules (channel pairing, memory store labels, ...) implement this and the
    composition root registers the providers through ``SyncContributions`` —
    sync never imports kind modules (cross-kind fence). Docs are deterministic
    payloads, and the area travels in both directions: serializing writes what
    this machine decided, applying upserts what another machine decided, and a
    document's disappearance is a decision too (``delete_docs``)."""

    @property
    def area(self) -> str:
        """Directory name under ``state/`` (kebab-case)."""
        ...

    async def export_docs(self) -> list[tuple[str, dict[str, object]]]:
        """Local state as (relative doc path without extension, payload) pairs.

        Everything this machine publishes for the area, and nothing else: a
        document the list does not name is one this machine no longer holds,
        which the serializer converges as the deletion it is."""
        ...

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        """Apply the working tree's docs to local state; returns (doc path,
        error) pairs, which the round reports as per-path failures and holds."""
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
    """Filesystem IO over the working tree the vault converges through, in the
    layout spec vault-sync lays out.

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
        """Prepare the working tree for this machine's serialization.

        It creates the directory and validates it. It MUST NOT clear anything:
        each area converges against local state in its own write method, which
        is what keeps the staged diff an honest account of what this vault
        changed."""

    @property
    def path(self) -> str: ...

    def mirror_trees_out(self) -> None:
        """Converge the bundle's ``knowledge/`` and ``skills/`` on the live
        trees. Symlinks and anything under a ``.git`` directory are skipped
        and logged, never copied.

        An implementation MAY hold back subtrees that are derived output — a
        folder every machine regenerates for itself (spec vault-sync FR-093).
        Held back means invisible in both directions: not copied out, and not
        removed from the tree either, so a copy an older build published is
        left inert rather than staged as a deletion the fleet would act on."""

    def tree_counts(self) -> list[tuple[str, int]]:
        """(subdir, file count) for each mirrored tree present in the bundle,
        plus ``machines`` once the bundle carries a registry."""

    def write_manifest(self, manifest: Manifest) -> None: ...

    def write_resource_docs(
        self,
        docs: Sequence[Mapping[str, object]],
        *,
        unserializable: Sequence[str] = (),
        withheld: Sequence[str] = (),
    ) -> None:
        """Converge ``resources/`` on ``docs`` — one deterministic YAML file
        per doc, writing only what changed and removing only what ``docs`` no
        longer names (never a held path).

        ``unserializable`` and ``withheld`` are both ``<kind>/<name>`` refs
        absent from ``docs`` for a reason that is not a deletion, so their
        paths survive: one could not be rendered, the other declined to travel
        row by row (``Kind.converges_row``)."""

    def read_resource_docs(self) -> list[ResourceDoc]: ...

    def write_state_docs(self, area: str, docs: Sequence[tuple[str, Mapping[str, object]]]) -> None:
        """Converge ``state/<area>/`` on ``docs``, differentially and touching
        no other area."""

    def write_credential_blobs(self, blobs: Mapping[str, bytes]) -> None:
        """Converge ``credentials/`` on ``blobs`` — one ``<ref>.enc`` per
        ciphertext blob, differentially."""

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
    """Storage for the single sync remote and the rounds run against it.

    A port rather than the concrete repository so the application layer keeps
    no infrastructure import; the composition root injects the SQLAlchemy one.

    ``record_run`` does two things as one step: it stores the round as the
    remote's *last*, which is what a status surface reads, and appends it to
    the *history*, which is what ``list_runs`` returns. One step rather than
    two calls, because a round the history missed would make the two disagree
    about the same moment.
    """

    async def get(self) -> BackupRemote | None: ...

    async def set(self, remote: BackupRemote) -> None: ...

    async def clear(self) -> None: ...

    async def record_run(self, run: ConvergeRun) -> None: ...

    async def refresh_run(self, run: ConvergeRun) -> bool:
        """Re-stamp the newest recorded round in place, if it is this one again.

        The one case: a confirmation the user has not answered, which the timer
        re-derives every interval (spec vault-sync FR-092). Ten identical rows
        carry no more information than one, so the round is written over the
        row that first reported it rather than appended. Returns False when
        there is no such row to refresh — the caller then records normally."""

    async def last_run(self) -> ConvergeRun | None: ...

    async def list_runs(self, limit: int = ...) -> list[RunRecord]: ...


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
