"""The one-flag rule on every write path but the one that moves it.

Spec provider-switching "Keep at most one internal-engine default". The flag is
moved by ``set_internal_default`` (``internal_default_ops``), which clears the
holder before it marks the target. Two other paths can write the flag, and
neither may leave a second one — which the partial unique index
``ux_provider_single_internal_default`` would otherwise answer with a raw
``IntegrityError``:

- **A direct write** — the kind-agnostic resource PATCH or POST. Refused with
  ``ProviderInternalDefaultTaken`` (409) through the kind's pre-write hooks
  (:func:`refusing_hooks`), so the holder keeps the flag and nothing is written.
- **A synced document** (spec vault-sync). Refusing it would hold the path for
  retry every round forever, so :class:`ProviderInternalDefaultNormaliser`
  settles it instead. A *move* lands: when the tree this round is applying
  also clears the flag on the local holder, another machine moved it. Any
  other clash — two machines each flagged a different connection between
  rounds — is settled by a tie-break every machine computes the same way: the
  connection whose uid sorts first keeps the flag. If that is the incoming
  one, the local holder is released and the document applies as written;
  otherwise the document applies with the flag cleared and the round is handed
  a note to report. "The flag already held here keeps it" was the rule before,
  and each machine answered it for itself: both kept their own, published the
  other as cleared, then received a clear for the one they kept, and ended
  with none.

  A release is handed back as a :class:`_ReleaseHolder` rather than written
  here: the applier runs it after the target's gate, just before the target's
  write, and reverts it if that write fails — so a target that cannot land
  leaves this machine its internal default.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from coffer.domain.provider.errors import ProviderInternalDefaultTaken
from coffer.domain.resource import Resource

_KIND = "provider"
_FLAG = "internal_default"


class _Rows(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> list[Resource]: ...


class _WritableRows(_Rows, Protocol):
    async def update_config(
        self,
        uid: str,
        new_config: dict[str, Any],
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource: ...


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


class _ReleaseHolder:
    """Clear the flag on ``holder``; revert puts back the config it had."""

    def __init__(self, rows: _WritableRows, holder: Resource, actor: str) -> None:
        self._rows = rows
        self._holder = holder
        self._actor = actor

    async def _write(self, config: dict[str, Any]) -> None:
        await self._rows.update_config(
            self._holder.uid, config, self._actor, allow_lifecycle_kind=True
        )

    async def apply(self) -> None:
        await self._write({**self._holder.config, _FLAG: False})

    async def revert(self) -> None:
        await self._write(dict(self._holder.config))


class ProviderInternalDefaultNormaliser:
    """Implements ``application.sync.ports.ImportNormaliser`` structurally."""

    kind = _KIND

    def __init__(self, rows: _WritableRows, *, actor: str = "sync") -> None:
        self._rows = rows
        self._actor = actor

    async def normalise(
        self,
        uid: str,
        config: Mapping[str, object],
        tree_config: Callable[[str], Awaitable[Mapping[str, object] | None]],
    ) -> tuple[dict[str, object], str | None, _ReleaseHolder | None]:
        out = dict(config)
        if out.get(_FLAG) is not True:
            return out, None, None
        holder = await other_holder(self._rows, uid)
        if holder is None:
            return out, None, None
        holder_in_tree = await tree_config(holder.uid)
        if holder_in_tree is not None and holder_in_tree.get(_FLAG) is not True:
            # A move made on another machine: its document for the holder
            # clears the flag in this same tree. Released with this document's
            # write rather than left to that document's own turn, which may
            # come after this one.
            return out, None, _ReleaseHolder(self._rows, holder, self._actor)
        if uid < holder.uid:
            # Two flags, no move: the uid that sorts first keeps it — the same
            # answer the other machine reaches when it meets this one's flag.
            return out, None, _ReleaseHolder(self._rows, holder, self._actor)
        out[_FLAG] = False
        return (
            out,
            f"applied without internal_default: connection {holder.name!r} "
            f"keeps the internal-engine default (its uid sorts first)",
            None,
        )
