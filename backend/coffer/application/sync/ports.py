"""Ports the sync application layer depends on; infrastructure implements them.

Keeping these as protocols lets ``application/sync`` stay free of the
filesystem and sqlite (Contract 2b) while the composition root injects the
concrete adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.serialization import ResourceDoc


class ImportGate(Protocol):
    """Per-kind validation the importing machine runs BEFORE upserting a doc
    (spec 010 import reconciliation). Raise ``CofferError`` to report the doc
    as a per-resource failure — the rest of the bundle still imports, and the
    user can re-run the import once this machine satisfies the precondition
    (e.g. the agent's config dir exists here).

    ``scope`` is the doc's ADR-045 activation scope, passed so a scope-aware
    gate can let a doc that is dormant here through untouched instead of
    failing it on a machine-local precondition that does not apply."""

    kind: str

    async def validate(self, config: Mapping[str, object], *, scope: Any = None) -> None: ...


class PostImportHook(Protocol):
    """Per-kind side-effect reconciliation run AFTER an import (spec 010
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


class BundlePort(Protocol):
    """Filesystem IO over one export bundle directory (spec 010 layout).

    Every method is synchronous blocking IO; the application layer runs them
    off the event loop."""

    def open_for_write(self) -> None:
        """Create (or clear) the bundle directory so an export is a snapshot
        of this vault rather than a merge with whatever was there before."""

    def require_readable(self) -> None:
        """Raise ``SyncBundleInvalid`` unless the path is an existing bundle."""

    @property
    def path(self) -> str: ...

    def mirror_trees_out(self) -> None:
        """Copy the live knowledge/memory/skill trees into the bundle."""

    def mirror_trees_in(self) -> None:
        """Copy the bundle's trees back into the live vault (never deleting)."""

    def tree_counts(self) -> list[tuple[str, int]]:
        """(subdir, file count) for each mirrored tree present in the bundle."""

    def write_manifest(self, manifest: Manifest) -> None: ...

    def read_manifest(self) -> Manifest | None: ...

    def write_resource_docs(self, docs: Sequence[Mapping[str, object]]) -> None:
        """Write one deterministic YAML file per doc under ``resources/``."""

    def read_resource_docs(self) -> list[ResourceDoc]: ...

    def write_state_docs(
        self, area: str, docs: Sequence[tuple[str, Mapping[str, object]]]
    ) -> None: ...

    def read_state_docs(self, area: str) -> list[tuple[str, dict[str, object]]]: ...

    def write_credential_blobs(self, blobs: Mapping[str, bytes]) -> None:
        """Write one ``<ref>.enc`` per ciphertext blob under ``credentials/``."""

    def read_credential_blobs(self) -> dict[str, bytes]: ...

    def list_files(self) -> list[str]:
        """All bundle-relative file paths (for the 'no key in the bundle' check)."""
