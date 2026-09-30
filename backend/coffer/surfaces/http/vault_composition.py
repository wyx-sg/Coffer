"""The vault layout's stores, built for the app lifespan (ADR
storage-is-five-classes-by-nature).

What the lifespan builds before any kind: the vault repository (created with
its first commit when it does not exist; a missing ``git`` is a startup error
naming it), this machine's id on every commit, the resource store over the
three class directories, ``derived/derived.db``, and the one validator every
vault write passes — resource documents and the state areas. Each kind's
wiring is handed the bundle and builds its own state store from it, registering
the follower that moves a state document with its owner
(``FileResourceRepo.add_follower``) and the owner listener that hints the
owner when its document changes (``FileResourceRepo.announce``).

Split out of :mod:`coffer.surfaces.http.app` for the file-size budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from coffer.application.vault.resource_rules import resource_rule
from coffer.application.vault.state_rules import state_rule
from coffer.application.vault.validation import VaultValidator
from coffer.domain.resource import Kind
from coffer.domain.vault.layout import RESOURCES, STATE
from coffer.infrastructure.persistence.derived_db import open_derived_db
from coffer.infrastructure.sync.identity import resolve_identity
from coffer.infrastructure.vault.git import GitMissing
from coffer.infrastructure.vault.instance import set_machine, vault_repository, vault_writer
from coffer.infrastructure.vault.resource_store import FileResourceRepo

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VaultStores:
    """The stores every kind's wiring reads from."""

    resources: FileResourceRepo
    derived_engine: AsyncEngine
    derived_sm: async_sessionmaker[AsyncSession]


def _machine_id() -> str | None:
    """This machine's id for the ``Coffer-Machine`` trailer, or ``None`` when
    it cannot be resolved (a commit is still made, naming no machine)."""
    try:
        return resolve_identity().machine_id or None
    except Exception:
        _log.warning("vault.machine_id_unresolved", exc_info=True)
        return None


async def build_vault_stores(kinds: dict[str, Kind]) -> VaultStores:
    """Ensure the vault repository and build the stores over it.

    ``kinds`` is the live registry the composition root fills while wiring:
    the store and the validator read it at every use, never a copy.
    """
    try:
        vault_repository().ensure()
    except GitMissing as exc:
        raise RuntimeError(str(exc)) from exc
    machine = _machine_id()
    set_machine(lambda: machine)
    resources = FileResourceRepo(kinds)
    validator = VaultValidator()
    validator.register(f"{RESOURCES}/", resource_rule(kinds, resources.head_owners))
    validator.register(f"{STATE}/", state_rule())
    vault_writer().set_validator(validator)
    derived_engine, derived_sm = await open_derived_db()
    return VaultStores(resources=resources, derived_engine=derived_engine, derived_sm=derived_sm)


__all__ = ["VaultStores", "build_vault_stores"]
