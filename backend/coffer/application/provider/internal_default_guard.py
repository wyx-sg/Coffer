"""The one-flag rule on every write path but the one that moves it.

Spec provider-switching "Keep at most one internal default connection". The flag is
moved by ``set_internal_default`` (``internal_default_ops``), which clears the
holder before it marks the target. Two other paths can write the flag, and
neither may leave a second one — which the partial unique index
``ux_provider_single_internal_default`` would otherwise answer with a raw
``IntegrityError``:

- **A direct write** — the kind-agnostic resource PATCH or POST. Refused with
  ``ProviderInternalDefaultTaken`` (409) through the kind's pre-write hooks
  (:func:`refusing_hooks`), so the holder keeps the flag and nothing is written.
- **A merged sync tree** that flags a second connection is refused by the
  vault's resource rule (the kind's exclusive flag), so the round stops on it
  and the person chooses (ADR sync-applies-clean-merges-and-stops-on-any-conflict).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from coffer.domain.provider.errors import ProviderInternalDefaultTaken
from coffer.domain.resource import Resource

_KIND = "provider"
_FLAG = "internal_default"


class _Rows(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> list[Resource]: ...


async def other_holder(rows: _Rows, uid: str | None) -> Resource | None:
    """The connection other than ``uid`` that carries the flag, if one does."""
    for r in await rows.list(kind=_KIND):
        if r.uid != uid and r.config.get(_FLAG) is True:
            return r
    return None


def refusing_hooks(
    rows: _Rows,
) -> tuple[
    Callable[[dict[str, Any]], Awaitable[None]],
    Callable[[Resource, dict[str, Any]], Awaitable[None]],
]:
    """``(validate_config, on_update_config)`` for the provider ``Kind``.

    Both refuse a config that sets the flag while another connection holds it.
    ``set_internal_default`` passes them, because it clears the holder first.
    """

    async def on_register(config: dict[str, Any]) -> None:
        if config.get(_FLAG) is True:
            holder = await other_holder(rows, None)
            if holder is not None:
                raise ProviderInternalDefaultTaken(holder.name)

    async def on_update(before: Resource, config: dict[str, Any]) -> None:
        if config.get(_FLAG) is True:
            holder = await other_holder(rows, before.uid)
            if holder is not None:
                raise ProviderInternalDefaultTaken(holder.name)

    return on_register, on_update
