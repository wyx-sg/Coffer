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
from collections.abc import Mapping, Sequence

import yaml

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.serialization import ResourceDoc, parse_resource_doc
from coffer.infrastructure.sync.paths import mirrored_trees as _default_mirrored_trees

_MANIFEST = "manifest.json"
_RESOURCES = "resources"
_CREDENTIALS = "credentials"

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


def _replace_tree(
    src: pathlib.Path, dst: pathlib.Path, exclude: frozenset[str] = frozenset()
) -> None:
    """Make ``dst`` a copy of ``src`` (empty when ``src`` is absent), skipping
    any basename in ``exclude``."""
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        ignore = shutil.ignore_patterns(*exclude) if exclude else None
        shutil.copytree(src, dst, ignore=ignore)
    else:
        dst.mkdir(parents=True, exist_ok=True)


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
        for subdir, live_root in self._trees:
            ws_tree = self._root / subdir
            if ws_tree.exists():
                _replace_tree(ws_tree, live_root, exclude=DERIVED_INDEX_NAMES)

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

    # --- resource docs -----------------------------------------------------

    def write_resource_docs(self, docs: Sequence[Mapping[str, object]]) -> None:
        target = self._root / _RESOURCES
        if target.exists():
            shutil.rmtree(target)
        for doc in docs:
            kind = str(doc["kind"])
            name = str(doc["name"])
            kind_dir = target / kind
            kind_dir.mkdir(parents=True, exist_ok=True)
            (kind_dir / f"{name}.yaml").write_text(
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
