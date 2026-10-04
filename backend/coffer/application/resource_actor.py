"""Who a resource write is for, as the store sees it (ADR
every-vault-write-is-a-validated-commit-naming-its-writer).

Every accepted vault write is one commit naming its writer and its audit
actor. ``ResourceRepo`` takes no actor — threading one through every method
would change every fake and every caller for a value only the file store
reads — so ``ResourceService`` states it for the duration of the repository
call instead, and the store reads it when it builds the commit. A write made
outside any service call (a boot pass, a migration) states nothing and is
committed as the daemon's own.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_ACTOR: ContextVar[str | None] = ContextVar("coffer_resource_actor", default=None)


@contextmanager
def acting_as(actor: str | None) -> Iterator[None]:
    """State ``actor`` for the repository calls made inside the block."""
    token = _ACTOR.set(actor)
    try:
        yield
    finally:
        _ACTOR.reset(token)


def current_actor() -> str | None:
    """The actor stated by the innermost ``acting_as``, or ``None``."""
    return _ACTOR.get()


__all__ = ["acting_as", "current_actor"]
