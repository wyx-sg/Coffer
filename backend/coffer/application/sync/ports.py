"""Ports the sync application layer depends on; infrastructure implements them.

Keeping these as protocols lets ``application/sync`` stay free of git, the
filesystem, and sqlite (Contract 2b) while the composition root injects the
concrete adapters.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import MachineEntry, MachineIdentity, Tombstone
from coffer.domain.sync.serialization import ResourceDoc


@dataclass(frozen=True)
class PullOutcome:
    """Result of a git pull/merge."""

    conflicted_paths: tuple[str, ...] = ()

    @property
    def is_conflict(self) -> bool:
        return bool(self.conflicted_paths)


class GitPort(Protocol):
    """Git transport over the sync workspace working tree."""

    def ensure_repo(self, remote: str, branch: str) -> None:
        """Clone the remote on first use, or point an existing tree at it."""

    def has_conflicts(self) -> bool: ...

    def conflicted_paths(self) -> list[str]: ...

    def commit_all(self, message: str) -> bool:
        """Stage everything and commit; return False if there was nothing to do."""

    def has_changes(self) -> bool:
        """Whether the working tree differs from HEAD (uncommitted changes)."""

    def head(self) -> str | None:
        """The workspace's current commit sha, or None before the first commit."""

    def remote_head(self, remote: str, branch: str) -> str | None:
        """The remote branch head sha (one ``ls-remote`` round trip), or None."""

    def pull(self, branch: str) -> PullOutcome: ...

    def push(self, branch: str) -> None: ...

    def resolve(self, strategy: str, paths: Sequence[str]) -> None:
        """Resolve conflicts with 'ours'/'theirs'/'resolved' then stage them."""


class WorkspacePort(Protocol):
    """Filesystem IO over the sync workspace (mirrors, manifest, docs, blobs)."""

    def mirror_trees_out(self) -> None:
        """Copy the live knowledge/memory trees into the workspace."""

    def mirror_trees_in(self) -> None:
        """Copy the workspace knowledge/memory trees back into the live vault."""

    def write_manifest(self, manifest: Manifest) -> None: ...

    def read_manifest(self) -> Manifest | None: ...

    def write_resource_docs(
        self, docs: Sequence[Mapping[str, object]], preserve: Collection[str] = ()
    ) -> None:
        """Replace ``resources/`` with one deterministic YAML file per doc,
        preserving the current workspace docs of quarantined ``preserve`` refs."""

    def read_resource_docs(self) -> list[ResourceDoc]: ...

    def write_tombstone(self, tombstone: Tombstone) -> None: ...

    def remove_tombstone(self, kind: str, name: str) -> None: ...

    def read_tombstones(self) -> list[Tombstone]: ...

    def write_state_docs(
        self,
        area: str,
        docs: Sequence[tuple[str, Mapping[str, object]]],
        owned_prefixes: Collection[str] = (),
    ) -> None:
        """Reconcile ``state/<area>/``: replace docs under ``owned_prefixes``,
        write ``docs``, preserve everything else verbatim."""

    def read_state_docs(self, area: str) -> list[tuple[str, dict[str, object]]]: ...

    def write_credential_blobs(self, blobs: Mapping[str, bytes]) -> None:
        """Replace ``credentials/`` with one ``<ref>.enc`` per ciphertext blob."""

    def read_credential_blobs(self) -> dict[str, bytes]: ...

    def list_files(self) -> list[str]:
        """All tracked workspace-relative paths (for the 'no key in medium' check)."""

    def write_machine_entry(self, entry: MachineEntry) -> None:
        """Write this machine's own ``machines/<id>.json`` registry entry."""

    def read_machine_entries(self) -> list[MachineEntry]:
        """All machine registry entries present in the workspace."""


class MachineIdentityPort(Protocol):
    """Persistence of this machine's stable identity singleton (ADR-043)."""

    async def get(self) -> MachineIdentity | None: ...

    async def create(self, machine_id: str, display_name: str) -> MachineIdentity: ...

    async def set_display_name(self, display_name: str) -> MachineIdentity: ...


class TombstoneLedgerPort(Protocol):
    """This machine's pending deletion records (spec 010 tombstones)."""

    async def record(self, kind: str, name: str) -> None: ...

    async def list(self) -> list[Tombstone]: ...

    async def remove(self, kind: str, name: str) -> None: ...

    async def prune_older_than(self, cutoff: datetime) -> int: ...


class SyncedStatePort(Protocol):
    """A module-owned shared-state area synced under ``state/<area>/``.

    Modules (channel pairing, MCP preferences, ...) implement this and the
    composition root registers the providers with the sync engine — sync never
    imports kind modules (cross-kind fence). Docs are deterministic payloads;
    export replaces the whole area (git's 3-way merge reconciles machines),
    import upserts into local state."""

    @property
    def area(self) -> str:
        """Directory name under ``state/`` (kebab-case)."""
        ...

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        """Local state as (relative doc path without extension, payload) pairs,
        plus the path PREFIXES this machine can vouch for. Export replaces only
        docs under owned prefixes — docs for entities this machine does not
        know locally (quarantined / not yet imported) are preserved verbatim,
        so an incomplete machine can never erase the fleet's state."""
        ...

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[str]:
        """Apply merged docs to local state; returns per-doc error strings."""
        ...


class CredentialSyncPort(Protocol):
    """Ciphertext-only credential IO + locked-ref detection (never the key)."""

    def list_refs(self) -> list[str]: ...

    def read_ciphertext(self, ref: str) -> bytes | None: ...

    def write_ciphertext(self, ref: str, blob: bytes) -> None: ...

    def locked_refs(self) -> list[str]:
        """Refs whose ciphertext cannot be decrypted on this machine (no/other key)."""


class MasterKeyPort(Protocol):
    """Out-of-band master-key transfer for the new-machine bootstrap."""

    def export_key(self) -> bytes | None: ...

    def install_key(self, key: bytes) -> None: ...


@dataclass
class ResourceSnapshot:
    """A resource as seen by export: identity + curation + validated config."""

    kind: str
    name: str
    description: str | None
    enabled: bool
    config: dict[str, object] = field(default_factory=dict)
