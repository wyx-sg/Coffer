"""Per-agent delivery results for a reach change, for the kinds that deliver.

The kind-agnostic ``PUT /resources/{uid}/scope`` asks here; a kind registers a
reporter at the composition root (the skill kind does), so the hub names no
kind."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.domain.resource import Resource
from coffer.surfaces.http.schemas import DeliveryResultOut

Reporter = Callable[[Resource], Awaitable[list[DeliveryResultOut]]]
_reporters: dict[str, Reporter] = {}


def register_delivery_reporter(kind: str, reporter: Reporter) -> None:
    _reporters[kind] = reporter


async def delivery_of(resource: Resource) -> list[DeliveryResultOut] | None:
    reporter = _reporters.get(resource.kind)
    return await reporter(resource) if reporter else None
