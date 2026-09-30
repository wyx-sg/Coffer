"""The Model providers list order, which is also fallback priority (spec
provider-switching "Order providers, and fail over in that order").

When an agent's model is offered by more than one enabled provider, the model
proxy tries the agent's own provider first and then the others in the order of
this list. The order is each connection's ``position``; a connection nobody has
placed sorts after the placed ones, by name. Reordering rewrites the positions
of every connection in one pass and files one audit row for the whole move.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import ProviderConfig, list_order
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


class ProviderOrderError(ValueError):
    """The uids given are not exactly the connections that exist."""


def ordered(rows: Sequence[Resource]) -> list[Resource]:
    """``rows`` in list order."""
    return sorted(
        rows,
        key=lambda r: list_order(r.name, ProviderConfig.model_validate(r.config).position),
    )


async def reorder(service: ProviderService, uids: Sequence[str], *, actor: str) -> list[Resource]:
    """Place the connections in ``uids`` order. ``uids`` must name every
    connection exactly once, so a stale page cannot drop one off the end."""
    rows = await service._resources.list(kind="provider")
    by_uid = {r.uid: r for r in rows}
    if len(uids) != len(set(uids)) or set(uids) != set(by_uid):
        raise ProviderOrderError("the order must name every provider exactly once")
    before = [r.uid for r in ordered(rows)]
    for index, uid in enumerate(uids):
        row = by_uid[uid]
        cfg = ProviderConfig.model_validate(row.config)
        if cfg.position == index:
            continue
        config = cfg.model_copy(update={"position": index}).model_dump(mode="json")
        await service._resources.update_config(uid, config, actor)
    if before != list(uids):
        await service._audit.record(
            AuditEventType.PROVIDER_REORDERED.value,
            actor=actor,
            details={"order": [by_uid[u].name for u in uids], "uids": list(uids)},
        )
    return ordered(await service._resources.list(kind="provider"))


__all__ = ["ProviderOrderError", "ordered", "reorder"]
