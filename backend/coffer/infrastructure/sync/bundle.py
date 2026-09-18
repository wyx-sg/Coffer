"""Filesystem IO over the working tree's bundle layout (spec and ADR vault-sync).

Layout::

    manifest.json                  # layout schema version; read before an apply
    knowledge/ skills/             # mirrors of the live file-backed trees
    resources/<kind>/<uid>.yaml    # one deterministic file per synced resource
    state/<area>/...yaml           # module-owned shared state
    credentials/<ref>.enc          # Fernet ciphertext, opt-in; never the key
    machines/<machine_id>.yaml     # one descriptor per machine, disjointly owned

Resource, state and machine docs are dumped with sorted keys so two exports of
an unchanged vault are byte-identical (spec vault-sync "Determinism"). Fernet
ciphertext is urlsafe-base64 ascii, so blobs are written as one text line —
readable, diffable, and never key material.

Every write is **differential**: a document is written only when its bytes
changed and removed only when the vault no longer holds it. That is normative
(spec vault-sync "Why deletion is safe") — the bundle is the git working tree
that gets three-way-merged, so clearing a directory and rewriting it from local
state would tell the merge "this vault deleted everything it never absorbed".
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import Any

import yaml

from coffer.domain.sync.errors import SyncBundleInvalid, SyncSerializationError
from coffer.domain.sync.manifest import MANIFEST_PATH, Manifest
from coffer.domain.sync.serialization import ResourceDoc, parse_resource_doc
from coffer.infrastructure.sync.paths import mirrored_trees as _default_mirrored_trees
from coffer.infrastructure.sync.paths import (
    non_converging_tree_paths as _default_excluded_paths,
)
from coffer.infrastructure.sync.tree_mirror import _converge_files, _mirror_tree

_logger = logging.getLogger(__name__)

_RESOURCES = "resources"
_CREDENTIALS = "credentials"
_STATE = "state"
_MACHINES = "machines"

#: Bundle subdirectories whose contents this export derives wholly from local
#: state, and which therefore converge differentially against it: everything
#: under them is written, kept or removed by the write methods below.
#:
#: ``machines/`` is deliberately absent. A machine writes its own descriptor
#: and no other's, so the registry is not derived from local state at all —
#: converging it here would delete every other machine's descriptor on every
#: export. Disjoint ownership is exactly what makes the registry unconflictable
#: (spec vault-sync "The registry is a derived view").
_OWNED_DIRS = (_RESOURCES, _STATE, _CREDENTIALS)


def _dump(doc: Mapping[str, object]) -> bytes:
    """One document's canonical bytes — sorted keys, so an unchanged document
    serializes to the same bytes and the differential write skips it."""
    return yaml.safe_dump(dict(doc), sort_keys=True, allow_unicode=True).encode("utf-8")


class Bundle:
    """Implements ``application.sync.ports.BundlePort`` structurally."""

    def __init__(
        self,
        root: pathlib.Path,
        trees: Sequence[tuple[str, pathlib.Path]] | None = None,
        held_paths: Callable[[], set[str]] | None = None,
        excluded: AbstractSet[str] | None = None,
    ) -> None:
        """``held_paths`` returns bundle-relative paths the export MUST NOT
        delete even though local state does not produce them — the retry and
        not-applicable sets from ``ConvergenceStatePort``. A document this
        vault failed to absorb is pending, not deleted, and removing it would
        publish a deletion the user never made.

        It sits on the constructor rather than on each write method, and beside
        ``trees`` rather than instead of it, for the same reason ``trees``
        does: it is one machine-wide fact that every area obeys — resources,
        state, credentials *and* the mirrored trees — so a per-method parameter
        would be the same argument repeated five times with five chances to
        forget one. It is a callable, not a set, because the holds are read
        asynchronously from convergence state while these methods are
        synchronous blocking IO: the caller hands over a view that resolves at
        write time instead of a snapshot taken before the round began.

        ``excluded`` holds bundle-relative directory prefixes inside the
        mirrored trees that this machine neither publishes nor deletes — the
        derived output of :data:`~coffer.infrastructure.sync.paths
        .NON_CONVERGING_TREE_PATHS`. It **defaults to that set** rather than to
        nothing on purpose: forgetting it at a construction site would silently
        resume the publishing this rule exists to stop, and there is no vault
        for which publishing derived output is the right answer. A caller may
        still pass ``frozenset()`` to mirror everything, which is what the
        tree-mirror's own tests want.
        """
        self._root = root
        # The file-backed trees to mirror. Injectable so each vault (and each
        # test) can point at its own live roots instead of the process-global
        # ``$COFFER_*_ROOT`` defaults.
        self._trees = list(trees) if trees is not None else _default_mirrored_trees()
        self._held_paths = held_paths
        self._excluded = frozenset(excluded) if excluded is not None else _default_excluded_paths()

    @property
    def path(self) -> str:
        return str(self._root)

    def _held_under(self, prefix: str) -> AbstractSet[str]:
        """The held paths inside ``prefix``, rebased relative to it — the form
        the convergence helpers compare destination entries against."""
        if self._held_paths is None:
            return frozenset()
        head = prefix.rstrip("/") + "/"
        return {p[len(head) :] for p in self._held_paths() if p.startswith(head)}

    def _excluded_under(self, prefix: str) -> AbstractSet[str]:
        """The excluded prefixes inside ``prefix``, rebased relative to it."""
        head = prefix.rstrip("/") + "/"
        return {p[len(head) :] for p in self._excluded if p.startswith(head)}

    # --- lifecycle ---------------------------------------------------------

    def open_for_write(self) -> None:
        if self._root.exists() and not self._root.is_dir():
            raise SyncBundleInvalid(str(self._root), "path exists and is not a directory")
        self._root.mkdir(parents=True, exist_ok=True)
        # Nothing is cleared: every area converges differentially below. All
        # this can usefully do is fail early on a directory the writes could
        # not converge anyway.
        for name in (*_OWNED_DIRS, _MACHINES):
            existing = self._root / name
            if existing.exists() and not existing.is_dir():
                raise SyncBundleInvalid(str(self._root), f"{name} exists and is not a directory")

    # --- live trees -> bundle ----------------------------------------------

    def mirror_trees_out(self) -> None:
        # Hidden entries are not filtered: with the derived indexes gone, every
        # regular file under a mirrored root is source of truth — the two
        # note/doc lanes plus the ``.raw/`` originals a re-conversion needs and
        # the ``.history/`` revisions that make an unattended rewrite
        # recoverable on the other machine too. What IS left out is anything
        # that is not a regular file of the vault's own: a symlink (its target
        # is not vault content, and following it would publish whatever it
        # points at) and anything under a ``.git`` directory (a nested
        # repository's internals, which git would refuse to track anyway).
        # Both are reported once per export rather than per file.
        self._root.mkdir(parents=True, exist_ok=True)
        skipped: list[str] = []
        for subdir, live_root in self._trees:
            skipped.extend(
                f"{subdir}/{rel}"
                for rel in _mirror_tree(
                    live_root,
                    self._root / subdir,
                    protected=self._held_under(subdir),
                    # Derived output: not published, and not deleted from the
                    # tree either if an older build put it there (spec
                    # vault-sync FR-093).
                    excluded=self._excluded_under(subdir),
                )
            )
        if skipped:
            _logger.warning(
                "sync: %d path(s) under the mirrored trees were skipped "
                "(symlinks or .git internals): %s",
                len(skipped),
                ", ".join(skipped[:20]) + (" …" if len(skipped) > 20 else ""),
            )

    def tree_counts(self) -> list[tuple[str, int]]:
        counts: list[tuple[str, int]] = []
        # ``machines/`` is reported alongside the mirrored trees — it is an
        # area of the bundle with a meaningful file count (how many machines
        # the registry holds) — but only once it exists, so a bundle that
        # carries no registry does not report an empty one.
        for subdir in (*(name for name, _root in self._trees), _MACHINES):
            tree = self._root / subdir
            if subdir == _MACHINES and not tree.exists():
                continue
            n = sum(1 for p in tree.rglob("*") if p.is_file()) if tree.exists() else 0
            counts.append((subdir, n))
        return counts

    # --- manifest ----------------------------------------------------------

    def write_manifest(self, manifest: Manifest) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        # ``MANIFEST_PATH`` rather than a literal: the version gate reads this
        # same path out of the remote, and a writer and a reader that disagree
        # about the name make the gate guard nothing.
        (self._root / MANIFEST_PATH).write_text(
            json.dumps(manifest.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    # --- resource docs -----------------------------------------------------

    def write_resource_docs(
        self,
        docs: Sequence[Mapping[str, object]],
        *,
        unserializable: Sequence[str] = (),
        withheld: Sequence[str] = (),
    ) -> None:
        """Converge ``resources/`` on ``docs``: ``docs`` is everything this
        vault publishes, so a document it does not name was deleted here —
        unless a held path says this vault never absorbed it.

        "Publishes", not "holds": the exporter withholds the kinds that are
        bound to one machine, and their documents are meant to leave the tree.
        A withheld kind is therefore *not* protected the way an unserializable
        row is, which is the correct treatment in both directions — the first
        export after a machine upgrades is what finally clears the channel
        documents an older build left in the shared tree, and no machine acts
        on that clearing, because the resource applier ignores those paths.

        ``unserializable`` is the escape hatch that keeps that sentence true.
        A row the exporter could not render is absent from ``docs`` for a
        reason that has nothing to do with the user, and converging on ``docs``
        alone would publish it as a deletion — the other machine would then
        drop the registration and release its credentials. "Could not render"
        is not "the user deleted it", so those paths are protected exactly like
        a held one.

        The file is named after the resource's **uid**, never its name (ADR
        resource-identity-is-an-immutable-uid). That one choice is what makes a
        rename survive the trip: the path is stable across it, so the change
        reaches the other machine as a modification of one file, and the
        receiving machine reads the new name out of the document. Keyed on the
        name, the same edit left the tree as a deletion beside an addition —
        and this method's own contract ("a document ``docs`` does not name was
        deleted here") is precisely what turned it into one.

        ``withheld`` is the second escape hatch, and it is the one that makes
        the paragraph above precise: it holds ``<kind>/<uid>`` for rows a
        **converging kind** declined to publish row by row (``Kind
        .converges_row`` — today, Coffer's own generated skill). Those are
        protected; a whole withheld *kind*'s documents are not. The asymmetry
        is about what the document is standing on at the other end. A `memory`
        row over there was derived from files that never travelled, so clearing
        it takes nothing away. A builtin skill row over there is backed by a
        real master folder that machine wrote itself and still delivers, so
        publishing its deletion would ask the fleet to tear down something
        live — and an older build, which has no row-level rule, would obey.

        One thing the uid key narrowed: a withheld path is protected only at a
        uid THIS machine holds, where the name-keyed version protected the
        label wherever it came from. Benign, because a build on this layout
        never publishes a guide document at all — the only way one exists in
        the tree is a machine that published it before FR-093, and that one
        registered it at the identity the document carried, so it is the same
        uid."""
        desired = {f"{doc['kind']}/{doc['uid']}.yaml": _dump(doc) for doc in docs}
        protected = (
            self._held_under(_RESOURCES)
            | {f"{ref}.yaml" for ref in unserializable}
            | {f"{ref}.yaml" for ref in withheld}
        )
        _converge_files(self._root / _RESOURCES, desired, protected=protected)

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
        """Converge one area. Only ``state/<area>/`` is touched, so a provider
        that is not registered on this machine keeps its area untouched rather
        than having it emptied."""
        prefix = f"{_STATE}/{area}"
        desired = {f"{rel}.yaml": _dump(doc) for rel, doc in docs}
        _converge_files(self._root / _STATE / area, desired, protected=self._held_under(prefix))

    # --- credential blobs --------------------------------------------------

    def write_credential_blobs(self, blobs: Mapping[str, bytes]) -> None:
        # Refs are namespaced with slashes (``channel/seatalk/app-secret``), so
        # a ``.enc`` file lives in a nested dir the convergence helper creates.
        desired = {f"{ref}.enc": blob for ref, blob in blobs.items()}
        _converge_files(
            self._root / _CREDENTIALS, desired, protected=self._held_under(_CREDENTIALS)
        )

    # --- machine descriptors -----------------------------------------------

    def write_machine_descriptor(
        self, machine_id: str, descriptor_doc: Mapping[str, object]
    ) -> None:
        """Write exactly ``machines/<machine_id>.yaml``, and touch no other
        machine's file.

        That restraint is the whole design of the registry (spec vault-sync
        "The registry is a derived view, not a synced table"). Because every
        machine owns a disjoint path, two machines can never stage a change to
        the same file, so git merges descriptors trivially and the registry
        needs no convergence machinery of its own — it is simply whatever
        ``machines/*.yaml`` currently holds. A write that swept the directory
        would delete the machines that were merely absent from this host's
        knowledge, and reintroduce precisely the conflict the layout avoids.
        """
        if not machine_id or "/" in machine_id or "\\" in machine_id or machine_id in {".", ".."}:
            raise ValueError(f"not a usable machine id: {machine_id!r}")
        target = self._root / _MACHINES
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{machine_id}.yaml"
        payload = _dump(descriptor_doc)
        # Skipping an unchanged descriptor is what keeps an idle machine from
        # staging a file on every round (spec vault-sync "Determinism").
        if path.exists() and path.read_bytes() == payload:
            return
        path.write_bytes(payload)

    def delete_machine_descriptor(self, machine_id: str) -> None:
        """Retire a machine's descriptor — the one write to another machine's
        path, and a deliberate one: a machine that is gone cannot remove its
        own row, so retiring it is a human act performed from a machine that
        remains."""
        if not machine_id or "/" in machine_id or "\\" in machine_id or machine_id in {".", ".."}:
            raise ValueError(f"not a usable machine id: {machine_id!r}")
        (self._root / _MACHINES / f"{machine_id}.yaml").unlink(missing_ok=True)

    def read_machine_descriptors(self) -> dict[str, dict[str, Any]]:
        """Every descriptor in the bundle, keyed by machine id.

        Tolerant on purpose: a descriptor is written by a possibly-newer build
        on someone else's machine, so one unreadable file is skipped rather
        than stopping the registry from rendering."""
        target = self._root / _MACHINES
        if not target.exists():
            return {}
        out: dict[str, dict[str, Any]] = {}
        for path in sorted(target.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                continue
            if isinstance(data, dict):
                out[path.stem] = data
        return out

    # --- inspection --------------------------------------------------------

    def list_files(self) -> list[str]:
        """All bundle-relative file paths — every area, ``machines/`` included,
        since the 'no key in the bundle' check must see everything written."""
        if not self._root.exists():
            return []
        return sorted(str(p.relative_to(self._root)) for p in self._root.rglob("*") if p.is_file())
