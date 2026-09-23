"""``resources/<kind>/<uid>.yaml`` — applying one registry row (spec vault-sync).

Its own module because it is the only applier with a two-way rule about what
an arriving document may change, and because the path it owns carries an
IDENTITY rather than a name — two arguments long enough that keeping them here
leaves ``appliers.py`` about the seam every applier shares rather than mostly
about this one.

The ``_ref_from`` / ``_identity_from`` pair lives here for the same reason:
both exist to read a uid out of a path or a document, and nothing else in the
bundle has an identity to read.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Mapping, Sequence

from coffer.application.resource_service import ResourceService
from coffer.application.sync.appliers_read import read_yaml
from coffer.application.sync.convergence_ops import is_inapplicable
from coffer.application.sync.ports import ImportGate, ImportNormaliser
from coffer.domain.error_base import CofferError
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.portability import expand_home


class ResourceApplier:
    """``resources/<kind>/<uid>.yaml`` — rows in the registry.

    **The path is the resource's uid, and that is what makes a rename safe**
    (ADR resource-identity-is-an-immutable-uid). The identity is immutable, so
    the path is stable across everything the user can change; a rename reaches
    this applier as an ``upsert`` of a path that was already there, carrying a
    different ``name`` inside. Keyed on the name, the same edit arrived as a
    ``remove`` of one path beside an ``upsert`` of another, and the ``remove``
    below is not a bookkeeping nicety — it runs the real
    ``ResourceService.delete``, whose cascade takes the kind-owned state
    (paired chats, capability preferences, skill bindings) and whose
    orphaned-credential release takes the secret nothing else cites. A rename
    was therefore destructive or survivable according to whether the new name
    sorted before or after the old one in the path-ordered apply loop.

    Upsert runs the kind's import gate first, so a document that cannot apply
    on this machine is reported before anything is written. Removal goes
    through ``ResourceService.delete``, which releases the credentials no
    remaining resource cites — the orphaned-credential path that seeded the
    2026-07-10 clobber.

    What an incoming document may change is narrower than what it used to be.
    It carries the resource — identity, description, config — and it does not
    carry the resource's **reach**: ``enabled`` and ``scope`` are one decision
    the user makes per machine, on the machine, and an arriving document never
    touches them here. A row that already exists keeps the reach it was given; a row
    that has just arrived takes the framework's own default, because a resource
    nobody on this machine has looked at yet has not been given a reach here
    either.

    A document of a kind that declares ``converges=False`` is ignored outright,
    upsert and removal alike. The exporter already withholds those, so this end
    of the rule only matters while the fleet is mixed — but that is exactly
    when it matters: a machine still on an older build keeps publishing them,
    and without this the ghost row arrives from the one direction the export
    fix cannot reach. Removal is skipped for the opposite reason: a derived row
    here was computed from THIS machine's agents, so a deletion in the tree has
    no standing over it.

    A row of a *converging* kind that the kind declines row by row
    (``Kind.converges_row`` — Coffer's own generated skill) is ignored on
    exactly the same terms, and the removal half is the one that had to be
    written down. Left to itself a deletion of `resources/skill/coffer-guide
    .yaml` would reach ``ResourceService.delete``, meet the skill kind's
    ``validate_delete`` guard, raise ``ResourceProtected`` — and the round,
    which catches ``CofferError`` and holds the path, would re-derive the same
    diff on the next tick and refuse it again, every tick, forever. The fix is
    not to soften the guard: a document about a row this machine does not
    publish is not this machine's to apply in *either* direction, so it never
    reaches the guard at all.

    The question is asked of the arriving document's config and of the local
    row's, and either answer is enough to ignore it. The document's, because a
    machine that has not yet seeded its own guide has no row to consult; the
    local row's, because a document written by a build that did not record the
    source still must not overwrite a folder this machine generated.
    """

    prefix = "resources/"

    def __init__(
        self,
        resources: ResourceService,
        *,
        worktree: pathlib.Path,
        gates: Sequence[ImportGate] = (),
        normalisers: Sequence[ImportNormaliser] = (),
        home: str | None,
        actor: str = "sync",
    ) -> None:
        self._resources = resources
        self._worktree = worktree
        self._gates = {gate.kind: gate for gate in gates}
        self._normalisers = {n.kind: n for n in normalisers}
        self._home = home
        self._actor = actor

    async def still_inapplicable(self, path: str) -> bool:
        """Whether a path held as not applicable here still cannot apply.

        Re-runs only the kind's import gate — the cheap, machine-local
        precondition (for an ``agent``: its config dir exists). Any other
        answer, a document gone from the tree included, lets the round retry
        the path, which is where a real failure is reported.
        """
        try:
            doc = await asyncio.to_thread(read_yaml, self._worktree / path)
            _uid, kind, _name = _identity_from(doc, path)
            gate = self._gates.get(kind)
            if gate is None:
                return False
            raw = doc.get("config")
            config: dict[str, object] = dict(raw) if isinstance(raw, Mapping) else {}
            if self._home:
                config = expand_home(config, self._home)
            await gate.validate(config)
        except CofferError as e:
            return is_inapplicable(e)
        except Exception:
            return False
        return False

    async def upsert(self, path: str) -> str | None:
        doc = await asyncio.to_thread(read_yaml, self._worktree / path)
        uid, kind, name = _identity_from(doc, path)
        raw_config = doc.get("config")
        config: dict[str, object] = dict(raw_config) if isinstance(raw_config, Mapping) else {}
        if self._home:
            config = expand_home(config, self._home)

        # By uid, never by name. The row this document is about is the row
        # that shares its identity, and a row with the same *name* may well be
        # a different resource someone created here independently — which is a
        # collision to report, not a row to overwrite.
        existing = await self._find(uid)
        if not self._converges(kind, config, existing):
            return None

        # A kind may rewrite what arrives before anything else sees it — the
        # provider kind's one internal-engine default (spec provider-switching
        # "Keep at most one internal-engine default"). A note means it did, and
        # travels back to the round to be reported; the path still applies.
        note: str | None = None
        normaliser = self._normalisers.get(kind)
        if normaliser is not None:
            config, note = await normaliser.normalise(
                uid, config, lambda other: self._tree_config(kind, other)
            )

        gate = self._gates.get(kind)
        if gate is not None:
            # The gate sees the config alone. It used to be handed the
            # document's scope as well, so a scope-aware gate could wave a
            # dormant doc past a machine-local precondition; reach does not
            # travel any more, and a gate that still wants that leniency reads
            # this machine's own row for it — the only place the answer was
            # ever true.
            await gate.validate(config)

        raw_description = doc.get("description")
        description = raw_description if isinstance(raw_description, str) else None
        if existing is None:
            # Registered at the identity the document carries rather than a
            # fresh one, so both machines go on holding the same resource. A
            # uid minted here would make this machine's copy a *different*
            # resource that happens to look the same, and the next round would
            # publish it as one.
            #
            # Whatever reach the framework gives a fresh row — the kind's
            # ``default_scope`` and the ``enabled`` default — is the right one.
            # This resource has just arrived; nobody on THIS machine has said
            # yet how far it should reach, and inventing an answer from the
            # other machine's would be exactly the silent re-answering the
            # document stopped carrying reach to prevent.
            await self._resources.register(
                kind,
                name,
                config,
                self._actor,
                description=description,
                allow_lifecycle_kind=True,
                uid=uid,
            )
        else:
            # A document that arrives at an identity this machine already
            # holds, spelling a different name, is a RENAME — not a new
            # resource, and not a name to ignore. It is a rename because the
            # identity is the uid: the user changed a label on the machine
            # they were sitting at, and the same resource is still the same
            # resource. Applying it through ``rename`` rather than writing the
            # column is what gives the kind its ``on_rename`` hook, so a kind
            # whose name is also a directory on disk moves that directory here
            # too — which is the whole reason the hook exists.
            if existing.name != name:
                await self._resources.rename(uid, name, self._actor)
            # Config and description only. The local ``enabled`` and ``scope``
            # are left exactly as this machine set them — that is the whole
            # decision, and it is a decision about *this* machine that an
            # incoming document has no standing to revise.
            await self._resources.update_config(
                uid,
                config,
                self._actor,
                description=description,
                allow_lifecycle_kind=True,
            )
        return note

    async def _tree_config(self, kind: str, uid: str) -> Mapping[str, object] | None:
        """The config of ``resources/<kind>/<uid>.yaml`` in this round's tree."""
        path = self._worktree / "resources" / kind / f"{uid}.yaml"
        if not path.is_file():
            return None
        raw = (await asyncio.to_thread(read_yaml, path)).get("config")
        return raw if isinstance(raw, Mapping) else None

    async def remove(self, path: str) -> None:
        # A removal has no document left to read, so the path is the only
        # thing that can name what went away — which is the other half of why
        # the path carries the identity rather than the label.
        kind, uid = _ref_from(path)
        if not self._resources.converges(kind):
            return
        existing = await self._find(uid)
        if existing is None:
            # Already gone here — two machines deleting the same resource is
            # agreement, not a failure. This is also what a tree written by the
            # previous bundle layout degrades to: its paths spell names, no
            # name is a uid this vault ever minted, and the deletions that
            # clear them out of the tree therefore match nothing and do
            # nothing.
            return
        # A removal carries no document, so the only config to ask about is the
        # local row's — which is the one that matters here anyway: what is
        # being protected is the row this machine generated.
        if not self._converges(kind, existing.config, existing):
            return
        await self._resources.delete(uid, self._actor)

    def _converges(
        self,
        kind: str,
        config: Mapping[str, object],
        existing: Resource | None,
    ) -> bool:
        """Whether this machine applies documents for this row at all.

        Both sides have to agree: an arriving document that describes derived
        output is not applied, and a local row that IS derived output is not
        revised by an arriving document either.
        """
        if not self._resources.converges_row(kind, config):
            return False
        return existing is None or self._resources.converges_row(kind, existing.config)

    async def _find(self, uid: str) -> Resource | None:
        try:
            return await self._resources.get(uid)
        except ResourceNotFound:
            return None


def _ref_from(path: str) -> tuple[str, str]:
    """Kind and uid, read out of ``resources/<kind>/<uid>.yaml``.

    The path alone, because the one caller is a removal and a removal has no
    document left to read.
    """
    parts = path.split("/")
    if len(parts) != 3:
        raise SyncSerializationError(f"{path} is not resources/<kind>/<uid>.yaml")
    return parts[1], parts[2].removesuffix(".yaml")


def _identity_from(doc: Mapping[str, object], path: str) -> tuple[str, str, str]:
    """Uid, kind and name for an upsert — read from the document, checked
    against the path.

    The document is the authority: it is the thing the exporter wrote and the
    thing git merged, and it is where the *name* lives at all. But the tree
    files it under its identity, so the two spellings have to agree, and a
    disagreement is refused rather than resolved. Picking a side would mean
    choosing between applying a document to a resource it does not claim to be
    and re-filing it under an identity it does not carry — and a hand-edited
    or half-copied tree is exactly the case where guessing costs the user a
    resource.

    A document with no ``uid`` at all lands here as the same refusal, and that
    is the right reading of it: it was written by a build on the previous
    bundle layout, and it names a resource this one cannot identify. The
    per-path failure is reported, the path is held so the next export does not
    publish it as a deletion, and the round carries on.
    """
    uid, kind, name = doc.get("uid"), doc.get("kind"), doc.get("name")
    if not (isinstance(uid, str) and uid):
        raise SyncSerializationError(f"{path} has no 'uid'")
    if not (isinstance(kind, str) and kind and isinstance(name, str) and name):
        raise SyncSerializationError(f"{path} has no 'kind'/'name'")
    path_kind, path_uid = _ref_from(path)
    if (path_kind, path_uid) != (kind, uid):
        raise SyncSerializationError(
            f"{path} is filed as {path_kind}/{path_uid} but the document says {kind}/{uid}"
        )
    return uid, kind, name
