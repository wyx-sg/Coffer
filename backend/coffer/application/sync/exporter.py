"""Serialize local vault state into the working tree (spec and ADR vault-sync).

Step 1 of a converge round. What comes out is exactly what this vault publishes
— but it is written **differentially**, never by clearing and rewriting: the
bundle is the git working tree that gets three-way-merged, so a wholesale
rewrite would tell the merge that every document this vault never absorbed had
been deliberately deleted. That rule is normative (spec vault-sync "Why deletion
is safe") and it lives in :mod:`coffer.infrastructure.sync.tree_mirror`; what
this module owes it is an honest and *complete* account of what this vault
publishes, area by area, on every export — "complete" measured against the rule
below, not against the registry, so that what is deliberately withheld is
withheld the same way every round and never looks like something that went
missing.

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

#: Resource kinds that never leave the machine they were registered on, and so
#: are never written into the bundle at all.
#:
#: A ``channel`` is an *inbound surface*: it is the webhook URL a platform
#: posts to, the tunnel that URL resolves through, and the port that tunnel
#: terminates on — three things that describe one host and mean nothing off it.
#: A channel that travelled would at best be inert on the other machine, its
#: callback pointing at a tunnel that machine does not run; at worst it would
#: come up and answer, and two machines would be replying in the same
#: conversation, each unaware of the other's turn. Neither outcome is something
#: the user asked for by pointing two machines at one remote.
#:
#: This is the exporting half of the rule. ``ResourceApplier`` holds the
#: importing half, and reads this same constant — one definition, because the
#: two halves are not independently correct.
MACHINE_LOCAL_KINDS = frozenset({"channel"})


class SyncExporter:
    """Writes the manifest, mirrored trees, resource docs, shared state, and
    (opt-in) credential ciphertext into a bundle directory.

    Two things a resource has are deliberately left behind.

    Its **reach** — ``enabled`` and ``scope``, which are one control in the UI
    and one decision to the user — is machine-local: it is set on the machine
    it applies to, and each machine sets its own. Publishing it would let this
    machine re-answer, silently and every round, a question the machine at the
    other end had already answered for itself.

    Its whole **document**, when its kind is in :data:`MACHINE_LOCAL_KINDS`: a
    resource bound to this host has nothing to say to another one."""

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
            if r.kind in MACHINE_LOCAL_KINDS:
                # Not a failure and not an unserializable row: this kind is
                # withheld on every export, so its absence from ``docs`` is the
                # steady state the bundle converges on rather than a gap to
                # protect. Protecting it would be the bug — it would pin the
                # stale channel documents an older build published into the
                # tree forever.
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
                area_docs, _owned = await provider.export_docs()
            except Exception as e:
                summary.failures.append((f"state/{provider.area}", str(e)))
                continue
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
