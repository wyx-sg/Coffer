"""Which connection Coffer's own engine runs on (spec internal-engine FR-005).

The engine runs on the connection the operator MARKED — the ``internal_default``
one — paired with a model chosen apart from it. Both halves are required, and a
missing one is an answer rather than a failure: with no model chosen, or no
connection marked, every internal pass is a clean no-op. The model no longer
lives on the connection, so there is no fallback to fall back TO.

That conjunction is the ENGINE's rule, which is why it is here and not in
``application.provider``: the requirement is the internal engine's, and a
requirement whose code lives in another package is misfiled. What the engine
cannot know is which provider row carries the flag — and it must not learn.
Reaching into ``application.provider`` from here would hand every consumer of
the engine (knowledge's tidy, memory's organise, vault-sync's conflict
resolver, chat's voice transcription) an indirect import of a kind none of them
names, and four cross-kind contracts would fail at once. So the provider kind
answers that one question through :class:`InternalDefaultConnectionPort`, which
the composition root satisfies.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Annotation-only: naming the provider kind's value object executes none of
    # its code, which is exactly what ``exclude_type_checking_imports`` exists
    # for. An import out here instead would re-form the chain described above.
    from coffer.domain.provider.config import ResolvedConnection


#: Reads the globally-chosen internal-engine model, or ``None`` when the
#: operator has chosen none. Called per resolution rather than captured, so a
#: model chosen (or forgotten) after wiring takes effect at once.
InternalModelReader = Callable[[], Awaitable[str | None]]


class InternalDefaultConnectionPort(Protocol):
    """The one question the engine puts to the provider kind.

    Pairing happens on the provider side because ``ResolvedConnection`` is that
    kind's own value object — only it may mint one — and because the
    ``internal_default`` flag lives on its rows. The engine decides WHETHER
    there is a connection to run on; the provider kind says WHICH.
    """

    async def internal_default_connection(self, model: str) -> ResolvedConnection | None: ...


async def resolve_internal_connection(
    *,
    read_model: InternalModelReader,
    connections: InternalDefaultConnectionPort,
) -> ResolvedConnection | None:
    """The connection + model Coffer's internal LLM engine runs on, or ``None``.

    ``None`` when no model is chosen OR no connection is marked — either way
    the internal engine is a clean no-op, and nothing is raised for a caller to
    have to swallow.
    """
    model = await read_model()
    if not model:
        return None
    return await connections.internal_default_connection(model)


class InternalEngineConnection:
    """The resolution above, bound to its two sources at composition time.

    Satisfies two ports structurally, because the consumers each coined their
    own name for the same question before there was one place to ask it:
    ``application.engine_ports.ModelSelectorPort`` (``get_default`` — knowledge's
    ingest and tidy, memory's organise) and
    ``infrastructure.sync.conflict_resolver.InternalModelPort``
    (``resolve_internal_connection`` — the converge round's arbiter). Neither
    port is this package's to rename, so this object answers to both rather
    than making the composition root wrap it twice.
    """

    def __init__(
        self,
        *,
        read_model: InternalModelReader,
        connections: InternalDefaultConnectionPort,
    ) -> None:
        self._read_model = read_model
        self._connections = connections

    async def get_default(self) -> ResolvedConnection | None:
        # The module-level function, not this class's same-named method below.
        return await resolve_internal_connection(
            read_model=self._read_model, connections=self._connections
        )

    async def resolve_internal_connection(self) -> ResolvedConnection | None:
        return await self.get_default()


__all__ = [
    "InternalDefaultConnectionPort",
    "InternalEngineConnection",
    "InternalModelReader",
    "resolve_internal_connection",
]
