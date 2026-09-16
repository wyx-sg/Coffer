"""Serialize local vault state into the working tree (spec and ADR vault-sync).

Step 1 of a converge round. What comes out is exactly what this vault publishes
— but it is written **differentially**, never by clearing and rewriting: the
bundle is the git working tree that gets three-way-merged, so a wholesale
rewrite would tell the merge that every document this vault never absorbed had
been deliberately deleted. That rule is normative (spec vault-sync "Why deletion
is safe") and it lives in :mod:`coffer.infrastructure.sync.tree_mirror`; what
this module owes it is an honest and *complete* account of what this vault
publishes, area by area, on every export. Complete means every resource of
every kind that converges: what is held back is a resource's reach and a
non-converging kind's rows, and both are held back the same way on every
export, so an absence in the tree is always a deletion somebody made rather
than a document that went missing.

Credentials are omitted unless the remote is configured to carry them, and even
then only Fernet ciphertext travels; the master key is never written.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import BundlePort, CredentialSyncPort, SyncedStatePort
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import AreaCount, ExportSummary
from coffer.domain.sync.portability import normalize_home
from coffer.domain.sync.serialization import resource_to_doc

# NOTE — there is no machine-local kind LIST here, and there is not going to be
# one. ``channel`` was the only entry it ever had: it was withheld because a
# channel arriving on a second machine was at best inert and at worst a second
# machine answering the same conversation. A channel now names the one machine
# whose daemon starts its adapter (spec channels ``## Where a channel runs``),
# which is the guard that objection was missing, so it travels like everything
# else.
#
# What decides now is ``Kind.converges``, declared where the kind is defined.
# The one kind that answers False is ``memory``: a partition row is derived
# from the agents installed on THIS machine, and spec memory FR-016 forbids it
# converging for a concrete reason — the second machine would show a partition
# naming a project root it may not have, with no facts behind it, because the
# derived tree stayed home. That is a rule about the kind, not about sync, so
# it is written on the kind and this module asks.
#
# The reverse transition is not free, and it is the exporting side that pays:
# a machine still running an older build keeps publishing the documents this
# one withholds, and each export from this build publishes their absence as a
# deletion. That is the cleanup rather than a loss — nothing at the other end
# is derived from them — but it is a deletion, so the publish-side guard is
# what stands between a mid-upgrade fleet and a surprise.


class SyncExporter:
    """Writes the manifest, mirrored trees, resource docs, shared state, and
    (opt-in) credential ciphertext into a bundle directory.

    One thing a resource has is deliberately left behind: its **reach** —
    ``enabled`` and ``scope``, which are one control in the UI and one decision
    to the user. Reach is machine-local: it is set on the machine it applies
    to, and each machine sets its own. Publishing it would let this machine
    re-answer, silently and every round, a question the machine at the other
    end had already answered for itself.

    Beyond that, only a kind that declares ``converges=False`` is held back —
    ``memory``, whose rows each machine derives for itself (spec memory FR-016). Every other kind is
    exported, ``channel`` included: a channel's
    own config now names the machine that runs it, so the document can travel
    without the adapter travelling with it."""

    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        state_providers: Sequence[SyncedStatePort] = (),
        *,
        home: str | None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._state_providers = list(state_providers)
        self._home = home

    async def export(self, bundle: BundlePort, *, with_credentials: bool = False) -> ExportSummary:
        summary = ExportSummary(path=bundle.path, credentials_included=with_credentials)
        docs: list[dict[str, object]] = []
        unserializable: list[str] = []
        for r in await self._resources.list():
            # The flag only ever withholds: a kind nobody declared anything
            # about keeps exporting, so this cannot quietly stop publishing a
            # kind by failing to recognise it.
            if not self._resources.converges(r.kind):
                continue
            try:
                config = dict(r.config)
                # The bundle speaks ${HOME}, never this machine's literal home.
                if self._home:
                    config = normalize_home(config, self._home)
                docs.append(
                    resource_to_doc(
                        kind=r.kind,
                        name=r.name,
                        description=r.description,
                        config=config,
                    )
                )
            except Exception as e:
                # Reported, not fatal — and its path is protected below, so a
                # row this build cannot render is never published as a
                # deletion the user never made.
                summary.failures.append((f"{r.kind}:{r.name}", str(e)))
                unserializable.append(f"{r.kind}/{r.name}")

        state_docs: list[tuple[str, list[tuple[str, dict[str, object]]]]] = []
        for provider in self._state_providers:
            try:
                area_docs = await provider.export_docs()
            except Exception as e:
                summary.failures.append((f"state/{provider.area}", str(e)))
                continue
            if self._home:
                # The same ``${HOME}`` rule a resource document gets: a state
                # area is as free to carry a path as a config is.
                home = self._home
                area_docs = [(rel, normalize_home(doc, home)) for rel, doc in area_docs]
            state_docs.append((provider.area, area_docs))

        blobs: dict[str, bytes] = {}
        if with_credentials:
            for ref in await asyncio.to_thread(self._credentials.list_refs):
                blob = await asyncio.to_thread(self._credentials.read_ciphertext, ref)
                if blob is not None:
                    blobs[ref] = blob

        # All filesystem IO runs off the event loop.
        await asyncio.to_thread(
            self._dump, bundle, docs, state_docs, blobs, with_credentials, unserializable
        )

        summary.areas.append(AreaCount("resources", len(docs)))
        for subdir, count in await asyncio.to_thread(bundle.tree_counts):
            summary.areas.append(AreaCount(subdir, count))
        for area, area_docs in state_docs:
            summary.areas.append(AreaCount(f"state/{area}", len(area_docs)))
        if with_credentials:
            summary.areas.append(AreaCount("credentials", len(blobs)))
        return summary

    def _dump(
        self,
        bundle: BundlePort,
        docs: list[dict[str, object]],
        state_docs: list[tuple[str, list[tuple[str, dict[str, object]]]]],
        blobs: dict[str, bytes],
        with_credentials: bool,
        unserializable: list[str],
    ) -> None:
        bundle.open_for_write()
        bundle.write_manifest(Manifest())
        bundle.write_resource_docs(docs, unserializable=unserializable)
        for area, area_docs in state_docs:
            bundle.write_state_docs(area, area_docs)
        bundle.mirror_trees_out()
        if with_credentials:
            # Converged even when empty, and NOT converged when this remote
            # does not carry credentials. Skipping an empty set would leave
            # the vault's last deleted credential standing in the tree
            # forever — its deletion could never be published — while
            # converging an area this remote opted out of would publish the
            # opting-out as a deletion of everyone else's blobs.
            bundle.write_credential_blobs(blobs)
