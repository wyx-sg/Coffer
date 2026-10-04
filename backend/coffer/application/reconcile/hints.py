"""Where ``Changed(kind, uid, op)`` hints come from: every write to a
resource row.

:class:`HintingResourceRepo` wraps the resource repository the
``ResourceService`` writes through. After each write that returns the resource
it emits one hint; a delete emits one marked ``op="delete"``. Because every
surface — REST, the CLI through the daemon — writes through
``ResourceService``, this one seam sees them all, and no kind has to remember
to announce its own writes.

A hint is an accelerator: the sink (:func:`fan_out` over
:meth:`Reconciler.hint` and the event broker) only brings the next pass
forward and announces the write, never blocks and never raises into it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from coffer.application.repos import ResourceRepo
from coffer.domain.reconcile import Changed, ChangeOp
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

_log = logging.getLogger(__name__)

HintSink = Callable[[Changed], None]


class HintingResourceRepo:
    """A :class:`ResourceRepo` that announces every write it performs."""

    def __init__(self, inner: ResourceRepo, sink: HintSink) -> None:
        self._inner = inner
        self._sink = sink

    def _emit(self, resource: Resource | None, *, op: ChangeOp = "upsert") -> None:
        if resource is None:
            return
        try:
            self._sink(Changed(resource.kind, resource.uid, op))
        except Exception:
            _log.exception("reconcile.hint_failed")

    # --- reads pass straight through ------------------------------------------

    async def find(self, uid: str) -> Resource | None:
        return await self._inner.find(uid)

    async def find_by_name(self, kind: str, name: str) -> Resource | None:
        return await self._inner.find_by_name(kind, name)

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return await self._inner.list(kind=kind, enabled=enabled)

    async def ensure_writable(self, uid: str) -> None:
        await self._inner.ensure_writable(uid)

    # --- writes announce themselves -------------------------------------------

    async def create(self, resource: Resource) -> Resource:
        created = await self._inner.create(resource)
        self._emit(created)
        return created

    async def update_config(
        self, uid: str, config: dict[str, Any], description: str | None
    ) -> Resource:
        updated = await self._inner.update_config(uid, config, description)
        self._emit(updated)
        return updated

    async def set_enabled(self, uid: str, enabled: bool) -> Resource:
        updated = await self._inner.set_enabled(uid, enabled)
        self._emit(updated)
        return updated

    async def update_scope(self, uid: str, scope: Scope | None) -> Resource | None:
        updated = await self._inner.update_scope(uid, scope)
        self._emit(updated)
        return updated

    async def rename(self, uid: str, new_name: str) -> Resource:
        renamed = await self._inner.rename(uid, new_name)
        self._emit(renamed)
        return renamed

    async def set_title(self, uid: str, title: str | None) -> Resource:
        updated = await self._inner.set_title(uid, title)
        self._emit(updated)
        return updated

    async def delete(self, uid: str) -> None:
        before = await self._inner.find(uid)
        await self._inner.delete(uid)
        self._emit(before, op="delete")


def fan_out(*sinks: HintSink) -> HintSink:
    """One sink that hands each hint to every one of ``sinks``, in order.

    Each sink is isolated: one that raises is logged and the rest still get
    the hint, so a failing listener never costs the reconciler its hint.
    """

    def sink(changed: Changed) -> None:
        for each in sinks:
            try:
                each(changed)
            except Exception:
                _log.exception("reconcile.hint_sink_failed")

    return sink


__all__ = ["HintSink", "HintingResourceRepo", "fan_out"]
