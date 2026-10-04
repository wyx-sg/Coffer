"""The one-flag rule on every write path but the one that moves it.

Spec provider-switching "Keep an independent speech-to-text default". The flag is
moved by its own setter (``set_transcribe_default`` in ``transcribe_default_ops``), which
clears the holder before it marks the target. Two other paths can write a flag, and neither
may leave a second one:

- **A direct write** — the kind-agnostic resource PATCH or POST. Refused with the flag's own
  error (409) through the kind's pre-write hooks (:func:`refusing_hooks`), so the holder
  keeps the flag and nothing is written.
- **A merged sync tree** that flags a second connection is refused by the vault's resource
  rule (the kind's ``exclusive_flags``), so the round stops on it and the person chooses
  (ADR sync-applies-clean-merges-and-stops-on-any-conflict).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from coffer.domain.errors import CofferError
from coffer.domain.provider.errors import ProviderTranscribeDefaultTaken
from coffer.domain.resource import Resource

_KIND = "provider"
#: Each flag only one connection may carry, with the error a second one is
#: refused with. ``Kind.exclusive_flags`` is built from these names.
EXCLUSIVE_FLAGS: dict[str, Callable[[str], CofferError]] = {
    "transcribe_default": ProviderTranscribeDefaultTaken,
}


class _Rows(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> list[Resource]: ...


async def other_holder(rows: _Rows, uid: str | None, flag: str) -> Resource | None:
    """The connection other than ``uid`` that carries ``flag``, if one does."""
    for r in await rows.list(kind=_KIND):
        if r.uid != uid and r.config.get(flag) is True:
            return r
    return None


def refusing_hooks(
    rows: _Rows,
) -> tuple[
    Callable[[dict[str, Any]], Awaitable[None]],
    Callable[[Resource, dict[str, Any]], Awaitable[None]],
]:
    """``(validate_config, on_update_config)`` for the provider ``Kind``.

    Both refuse a config that sets a flag while another connection holds it.
    The setters pass them, because they clear the holder first.
    """

    async def check(uid: str | None, config: dict[str, Any]) -> None:
        for flag, error in EXCLUSIVE_FLAGS.items():
            if config.get(flag) is True:
                holder = await other_holder(rows, uid, flag)
                if holder is not None:
                    raise error(holder.name)

    async def on_register(config: dict[str, Any]) -> None:
        await check(None, config)

    async def on_update(before: Resource, config: dict[str, Any]) -> None:
        await check(before.uid, config)

    return on_register, on_update
