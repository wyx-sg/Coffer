"""The vault layout's stores, built in the test's own HOME.

Every test runs with its own ``HOME`` (``tests/conftest.py``), so the vault
repository, ``local/`` and ``derived/`` these build are the test's alone —
the same classes the composition root builds, with the same validator on the
writer, so a test exercises what the daemon runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.vault.resource_rules import resource_rule
from coffer.application.vault.state_rules import state_rule
from coffer.application.vault.validation import VaultValidator
from coffer.domain.resource import Kind
from coffer.infrastructure.persistence.derived_db import (
    DerivedBase,
    derived_db_path,
    open_derived_db,
    prepare_derived_db,
)
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.resource_store import FileResourceRepo


def make_resource_repo(
    kinds: Mapping[str, Kind] | None = None, *, home: Path | None = None
) -> FileResourceRepo:
    """The file resource store over this HOME, the vault's validator wired.

    Pass the same ``kinds`` dict the ``ResourceService`` gets, when the test
    depends on a kind's storage class, default scope or config schema; without
    it every resource is filed in the vault and its config passed whole. Pass
    ``home`` for a test that builds two independent machines side by side.
    """
    registry: Mapping[str, Kind] = kinds if kinds is not None else {}
    repo = FileResourceRepo(registry, home=home)
    validator = VaultValidator()
    validator.register("resources/", resource_rule(registry, repo.head_owners))
    validator.register("state/", state_rule())
    vault_writer(vault_root(home)).set_validator(validator)
    return repo


@asynccontextmanager
async def derived_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session maker on this HOME's ``derived/derived.db``."""
    engine, sm = await open_derived_db()
    try:
        yield sm
    finally:
        await engine.dispose()


_DERIVED: dict[str, async_sessionmaker[AsyncSession]] = {}


def derived_sm() -> async_sessionmaker[AsyncSession]:
    """``derived.db``'s session maker for this HOME, its schema created —
    synchronous, so a sync fixture or a dependency-override lambda can use
    it, and one per HOME, so a test asking twice shares one engine."""
    path = derived_db_path()
    key = str(path)
    if key not in _DERIVED:
        prepare_derived_db(path)
        sync_engine = create_engine(f"sqlite:///{path}")
        DerivedBase.metadata.create_all(sync_engine)
        sync_engine.dispose()
        _DERIVED[key] = session_maker(
            create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{path}")
        )
    return _DERIVED[key]


__all__ = ["derived_db", "derived_sm", "make_resource_repo"]
