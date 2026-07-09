"""Ports the sync application layer depends on; infrastructure implements them.

Keeping these as protocols lets ``application/sync`` stay free of git, the
filesystem, and sqlite (Contract 2b) while the composition root injects the
concrete adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import MachineEntry, MachineIdentity
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

    def write_resource_docs(self, docs: Sequence[Mapping[str, object]]) -> None:
        """Replace ``resources/`` with one deterministic YAML file per doc."""

    def read_resource_docs(self) -> list[ResourceDoc]: ...

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
