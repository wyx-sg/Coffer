"""Filesystem IO over the sync workspace (spec 010).

Mirrors the live knowledge/memory trees in and out, and reads/writes the
manifest, the per-resource YAML docs, and the per-ref ciphertext blobs. Resource
docs are dumped with sorted keys so two machines holding the same logical
resource produce byte-identical files (no spurious git conflict).

Fernet ciphertext is urlsafe-base64 ascii, so blobs are written as a single text
line — diffable and git-friendly — not opaque binary.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

import yaml

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import MachineEntry, Tombstone
from coffer.domain.sync.serialization import ResourceDoc, parse_resource_doc
from coffer.infrastructure.sync.paths import mirrored_trees as _default_mirrored_trees
from coffer.infrastructure.sync.tree_mirror import _mirror_tree, _replace_tree

_MANIFEST = "manifest.json"
_RESOURCES = "resources"
_CREDENTIALS = "credentials"
_MACHINES = "machines"
_TOMBSTONES = "tombstones"
_STATE = "state"

#: Files that are *derived* from the source-of-truth files and must NOT be
#: synced — they would differ per machine and cause spurious same-path
#: conflicts, so they are excluded from the mirror (kept machine-local). The
#: legacy ``MEMORY.md`` index is no longer regenerated, but stays excluded so a
#: leftover copy from a pre-lane build never conflicts across machines.
#: The organizer's ``INDEX.md`` (each machine regenerates it from the synced
#: topic docs) and its store-root ``consolidation-log.md`` (a per-machine
#: changelog) are likewise derived/machine-local — the topic docs themselves DO
#: sync as the source of truth.
DERIVED_INDEX_NAMES = frozenset({"MEMORY.md", "INDEX.md", "consolidation-log.md"})


class Workspace:
    """Implements ``application.sync.ports.WorkspacePort`` structurally."""

    def __init__(
        self,
        root: pathlib.Path,
        trees: Sequence[tuple[str, pathlib.Path]] | None = None,
    ) -> None:
        self._root = root
        # The file-backed trees to mirror. Injectable so each machine (and each
        # test) can point at its own live roots instead of the process-global
        # ``$COFFER_*_ROOT`` defaults.
        self._trees = list(trees) if trees is not None else _default_mirrored_trees()

    # --- live trees <-> workspace -----------------------------------------

    def mirror_trees_out(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for subdir, live_root in self._trees:
            # Derived indexes never enter the workspace, so they never conflict.
            _replace_tree(live_root, self._root / subdir, exclude=DERIVED_INDEX_NAMES)

    def mirror_trees_in(self) -> None:
        # Diff-aware on the live side: a no-change import must neither storm
        # the file watcher nor delete the machine-local derived indexes.
        for subdir, live_root in self._trees:
            ws_tree = self._root / subdir
            if ws_tree.exists():
                _mirror_tree(ws_tree, live_root, exclude=DERIVED_INDEX_NAMES)

    # --- manifest ----------------------------------------------------------

    def write_manifest(self, manifest: Manifest) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / _MANIFEST).write_text(
            json.dumps(manifest.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def read_manifest(self) -> Manifest | None:
        path = self._root / _MANIFEST
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SyncSerializationError(f"manifest is not valid JSON: {e}") from e
        return Manifest.from_dict(data)

    # --- machine registry ----------------------------------------------------

    def write_machine_entry(self, entry: MachineEntry) -> None:
        """Write this machine's own registry entry (never another machine's).

        Write-to-temp + atomic rename, so a crash mid-write can never leave a
        truncated entry behind (a reader may run concurrently)."""
        target = self._root / _MACHINES
        target.mkdir(parents=True, exist_ok=True)
        final = target / f"{entry.machine_id}.json"
        tmp = target / f".{entry.machine_id}.json.tmp"
        tmp.write_text(
            json.dumps(entry.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(final)

    def read_machine_entries(self) -> list[MachineEntry]:
        """All parseable machine registry entries.

        The registry is informational, so one corrupt entry (hand-edited repo,
        interrupted writer on an old build) must never halt syncing the vault:
        invalid files are skipped, and a machine whose own entry is unreadable
        simply rewrites it on its next run."""
        target = self._root / _MACHINES
        if not target.exists():
            return []
        entries: list[MachineEntry] = []
        for path in sorted(target.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "machine_id" not in data:
                    continue
                entries.append(MachineEntry.from_dict(data))
            except (json.JSONDecodeError, OSError, KeyError, ValueError):
                continue
        return entries

    # --- resource docs -----------------------------------------------------

    def write_resource_docs(
        self,
        docs: Sequence[Mapping[str, object]],
        preserve: Collection[str] = (),
    ) -> None:
        """Replace ``resources/`` with one YAML per doc.

        ``preserve`` names quarantined ``<kind>:<name>`` refs whose CURRENT
        workspace doc must survive verbatim — their import failed here, so the
        local vault holds nothing (or a stale row) and must never overwrite or
        drop the remote intent (spec 010 quarantine)."""
        target = self._root / _RESOURCES
        preserved: dict[tuple[str, str], str] = {}
        for ref in preserve:
            kind, _, name = ref.partition(":")
            path = target / kind / f"{name}.yaml"
            if path.exists():
                preserved[(kind, name)] = path.read_text(encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
        for doc in docs:
            kind = str(doc["kind"])
            name = str(doc["name"])
            if (kind, name) in preserved:
                continue
            kind_dir = target / kind
            kind_dir.mkdir(parents=True, exist_ok=True)
            (kind_dir / f"{name}.yaml").write_text(
                yaml.safe_dump(dict(doc), sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )
        for (kind, name), text in preserved.items():
            path = target / kind / f"{name}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def read_resource_docs(self) -> list[ResourceDoc]:
        target = self._root / _RESOURCES
        if not target.exists():
            return []
        docs: list[ResourceDoc] = []
        for path in sorted(target.rglob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                raise SyncSerializationError(f"{path.name} is not valid YAML: {e}") from e
            if not isinstance(raw, Mapping):
                raise SyncSerializationError(f"{path.name} is not a mapping")
            docs.append(parse_resource_doc(raw))
        return docs

    # --- tombstones ----------------------------------------------------------

    def write_tombstone(self, tombstone: Tombstone) -> None:
        path = self._root / _TOMBSTONES / _RESOURCES / tombstone.kind / f"{tombstone.name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{tombstone.name}.json.tmp"
        tmp.write_text(
            json.dumps(tombstone.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    def remove_tombstone(self, kind: str, name: str) -> None:
        path = self._root / _TOMBSTONES / _RESOURCES / kind / f"{name}.json"
        path.unlink(missing_ok=True)

    def read_tombstones(self) -> list[Tombstone]:
        """All parseable tombstones. A corrupt file is skipped — the resource
        then survives (the safe direction) and the deleting machine's next
        export rewrites the tombstone."""
        base = self._root / _TOMBSTONES / _RESOURCES
        if not base.exists():
            return []
        out: list[Tombstone] = []
        for path in sorted(base.glob("*/*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                raw_by = data.get("by")
                out.append(
                    Tombstone(
                        kind=path.parent.name,
                        name=path.stem,
                        deleted_at=datetime.fromisoformat(str(data["deleted_at"])),
                        by=str(raw_by) if raw_by else None,
                    )
                )
            except (json.JSONDecodeError, OSError, KeyError, ValueError):
                continue
        return out

    # --- per-machine overrides -------------------------------------------------

    def _overrides_dir(self, machine_id: str) -> pathlib.Path:
        return self._root / _MACHINES / machine_id / "overrides"

    def write_override(
        self, machine_id: str, kind: str, name: str, patch: Mapping[str, object]
    ) -> None:
        path = self._overrides_dir(machine_id) / kind / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(dict(patch), sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )

    def remove_override(self, machine_id: str, kind: str, name: str) -> None:
        (self._overrides_dir(machine_id) / kind / f"{name}.yaml").unlink(missing_ok=True)

    def read_overrides(self, machine_id: str) -> dict[tuple[str, str], dict[str, object]]:
        """This machine's own merge patches, keyed by (kind, name). Corrupt
        files are skipped (the owner rewrites them via the override surface)."""
        base = self._overrides_dir(machine_id)
        if not base.exists():
            return {}
        out: dict[tuple[str, str], dict[str, object]] = {}
        for path in sorted(base.glob("*/*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                continue
            if isinstance(data, dict):
                out[(path.parent.name, path.stem)] = data
        return out

    # --- shared-state areas ---------------------------------------------------

    def write_state_docs(
        self,
        area: str,
        docs: Sequence[tuple[str, Mapping[str, object]]],
        owned_prefixes: Collection[str] = (),
        preserve: Collection[str] = (),
    ) -> None:
        """Prefix-scoped reconcile, never a blanket replace: docs outside
        ``owned_prefixes`` belong to entities this machine does not know
        locally (quarantined / not yet imported) and must survive its export —
        a blanket rmtree would erase the fleet's state and ping-pong forever
        against the machines that keep re-publishing it."""
        target = self._root / _STATE / area
        kept = set(preserve)
        wanted = {rel for rel, _doc in docs if rel not in kept}
        if target.exists():
            for path in sorted(target.rglob("*.yaml")):
                rel = path.relative_to(target).with_suffix("").as_posix()
                # Boundary-aware: prefix "jira" owns "jira" and "jira/...",
                # never the sibling "jira-internal" (a bare startswith would
                # cross-delete docs of servers this machine does not hold).
                owned = any(
                    rel == prefix.rstrip("/") or rel.startswith(prefix.rstrip("/") + "/")
                    for prefix in owned_prefixes
                )
                if owned and rel not in wanted and rel not in kept:
                    path.unlink(missing_ok=True)
        for rel, doc in docs:
            if rel in kept:
                continue  # import failed here: the foreign doc must survive
            path = target / f"{rel}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump(dict(doc), sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )

    def read_state_docs(self, area: str) -> list[tuple[str, dict[str, object]]]:
        """All parseable docs in an area; corrupt files are skipped (state is
        re-exported by its owner on its next run)."""
        target = self._root / _STATE / area
        if not target.exists():
            return []
        out: list[tuple[str, dict[str, object]]] = []
        for path in sorted(target.rglob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                continue
            if isinstance(data, dict):
                out.append((path.relative_to(target).with_suffix("").as_posix(), data))
        return out

    # --- credential blobs --------------------------------------------------

    def write_credential_blobs(self, blobs: Mapping[str, bytes]) -> None:
        target = self._root / _CREDENTIALS
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        for ref, blob in blobs.items():
            # Refs are namespaced with slashes (e.g. ``channel/seatalk/app-secret``),
            # so the ``.enc`` file lives in a nested dir that must exist first.
            dest = target / f"{ref}.enc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)

    def read_credential_blobs(self) -> dict[str, bytes]:
        target = self._root / _CREDENTIALS
        if not target.exists():
            return {}
        # Walk recursively and rebuild the full slash ref from the path relative
        # to ``credentials/`` minus the ``.enc`` suffix, so namespaced refs round-trip.
        return {
            path.relative_to(target).with_suffix("").as_posix(): path.read_bytes()
            for path in sorted(target.rglob("*.enc"))
        }

    # --- inspection --------------------------------------------------------

    def list_files(self) -> list[str]:
        files: list[str] = []
        for path in self._root.rglob("*"):
            if path.is_file() and ".git" not in path.relative_to(self._root).parts:
                files.append(str(path.relative_to(self._root)))
        return sorted(files)
