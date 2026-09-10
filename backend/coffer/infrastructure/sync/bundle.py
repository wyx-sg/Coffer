"""Filesystem IO over one export bundle directory (spec and ADR vault-export-import).

Layout::

    manifest.json                  # bundle schema version + creation time
    knowledge/ memory/ skills/     # mirrors of the live file-backed trees
    resources/<kind>/<name>.yaml   # one deterministic file per config resource
    state/<area>/...yaml           # module-owned shared state
    credentials/<ref>.enc          # Fernet ciphertext, opt-in; never the key

Resource and state docs are dumped with sorted keys so two exports of an
unchanged vault are byte-identical (spec vault-export-import "Determinism"). Fernet ciphertext
is urlsafe-base64 ascii, so blobs are written as one text line — readable,
diffable, and never key material.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from collections.abc import Mapping, Sequence

import yaml

from coffer.domain.sync.errors import SyncBundleInvalid, SyncSerializationError
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.serialization import ResourceDoc, parse_resource_doc
from coffer.infrastructure.sync.paths import mirrored_trees as _default_mirrored_trees
from coffer.infrastructure.sync.tree_mirror import _mirror_tree

_MANIFEST = "manifest.json"
_RESOURCES = "resources"
_CREDENTIALS = "credentials"
_STATE = "state"

#: Files *derived* from the source-of-truth files. They are regenerated on
#: whichever machine needs them, so carrying them would only make two vaults
#: differ in ways neither user authored: the legacy ``MEMORY.md`` index, the
#: organizer's ``INDEX.md``, and the per-machine ``consolidation-log.md``. The
#: topic docs they are derived FROM do travel.
DERIVED_INDEX_NAMES = frozenset({"MEMORY.md", "INDEX.md", "consolidation-log.md"})

#: Bundle subdirectories an export owns wholesale. ``open_for_write`` clears
#: them so an export is a snapshot of this vault, never a merge with an older
#: bundle that happened to live at the same path.
_OWNED_DIRS = (_RESOURCES, _STATE, _CREDENTIALS)


class Bundle:
    """Implements ``application.sync.ports.BundlePort`` structurally."""

    def __init__(
        self,
        root: pathlib.Path,
        trees: Sequence[tuple[str, pathlib.Path]] | None = None,
    ) -> None:
        self._root = root
        # The file-backed trees to mirror. Injectable so each vault (and each
        # test) can point at its own live roots instead of the process-global
        # ``$COFFER_*_ROOT`` defaults.
        self._trees = list(trees) if trees is not None else _default_mirrored_trees()

    @property
    def path(self) -> str:
        return str(self._root)

    # --- lifecycle ---------------------------------------------------------

    def open_for_write(self) -> None:
        if self._root.exists() and not self._root.is_dir():
            raise SyncBundleInvalid(str(self._root), "path exists and is not a directory")
        self._root.mkdir(parents=True, exist_ok=True)
        for name in _OWNED_DIRS:
            shutil.rmtree(self._root / name, ignore_errors=True)
        for subdir, _live_root in self._trees:
            shutil.rmtree(self._root / subdir, ignore_errors=True)

    def require_readable(self) -> None:
        if not self._root.exists():
            raise SyncBundleInvalid(str(self._root), "directory does not exist")
        if not self._root.is_dir():
            raise SyncBundleInvalid(str(self._root), "path is not a directory")
        if not (self._root / _MANIFEST).exists():
            raise SyncBundleInvalid(str(self._root), "no manifest.json")

    # --- live trees <-> bundle ---------------------------------------------

    def mirror_trees_out(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for subdir, live_root in self._trees:
            _mirror_tree(live_root, self._root / subdir, exclude=DERIVED_INDEX_NAMES)

    def mirror_trees_in(self) -> None:
        # ``delete_missing=False``: import never deletes, so a note this vault
        # holds and the bundle does not survives the import untouched.
        for subdir, live_root in self._trees:
            tree = self._root / subdir
            if tree.exists():
                _mirror_tree(tree, live_root, exclude=DERIVED_INDEX_NAMES, delete_missing=False)

    def tree_counts(self) -> list[tuple[str, int]]:
        counts: list[tuple[str, int]] = []
        for subdir, _live_root in self._trees:
            tree = self._root / subdir
            n = sum(1 for p in tree.rglob("*") if p.is_file()) if tree.exists() else 0
            counts.append((subdir, n))
        return counts

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
        if not isinstance(data, Mapping):
            raise SyncSerializationError("manifest is not a mapping")
        return Manifest.from_dict(data)

    # --- resource docs -----------------------------------------------------

    def write_resource_docs(self, docs: Sequence[Mapping[str, object]]) -> None:
        target = self._root / _RESOURCES
        for doc in docs:
            kind_dir = target / str(doc["kind"])
            kind_dir.mkdir(parents=True, exist_ok=True)
            (kind_dir / f"{doc['name']}.yaml").write_text(
                yaml.safe_dump(dict(doc), sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )

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

    # --- shared-state areas ------------------------------------------------

    def write_state_docs(self, area: str, docs: Sequence[tuple[str, Mapping[str, object]]]) -> None:
        target = self._root / _STATE / area
        for rel, doc in docs:
            path = target / f"{rel}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump(dict(doc), sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )

    def read_state_docs(self, area: str) -> list[tuple[str, dict[str, object]]]:
        """All parseable docs in an area; a corrupt file is skipped rather than
        failing the whole import (per-doc failures are reported, not fatal)."""
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
        target.mkdir(parents=True, exist_ok=True)
        for ref, blob in blobs.items():
            # Refs are namespaced with slashes (``channel/seatalk/app-secret``),
            # so the ``.enc`` file lives in a nested dir that must exist first.
            dest = target / f"{ref}.enc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)

    def read_credential_blobs(self) -> dict[str, bytes]:
        target = self._root / _CREDENTIALS
        if not target.exists():
            return {}
        # Rebuild the full slash ref from the path relative to ``credentials/``
        # minus the ``.enc`` suffix, so namespaced refs round-trip.
        return {
            path.relative_to(target).with_suffix("").as_posix(): path.read_bytes()
            for path in sorted(target.rglob("*.enc"))
        }

    # --- inspection --------------------------------------------------------

    def list_files(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(str(p.relative_to(self._root)) for p in self._root.rglob("*") if p.is_file())
