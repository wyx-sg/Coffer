"""What each kind contributes to vault convergence, collected explicitly.

Sync (spec vault-sync) is wired last, after every kind, because a kind may
publish a synced state area, gate or normalise what is imported onto this machine, or
re-apply on-disk side-effects after an import. The composition root builds one
:class:`SyncContributions`, hands it to each wiring step that has something to
contribute, and passes it to ``start_sync`` at the end — so the contributions
travel as a parameter, and the order they were made in is the order the
lifespan reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from coffer.application.sync.ports import (
    ImportGate,
    ImportNormaliser,
    PostImportHook,
    SyncedStatePort,
)


@dataclass
class SyncContributions:
    """Mutable collector: each kind appends during wiring; sync reads at the end."""

    state_providers: list[SyncedStatePort] = field(default_factory=list)
    import_gates: list[ImportGate] = field(default_factory=list)
    import_normalisers: list[ImportNormaliser] = field(default_factory=list)
    post_import_hooks: list[PostImportHook] = field(default_factory=list)
