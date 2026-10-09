"""``provider`` Kind wiring for the composition root (spec provider-switching).

A provider profile is a pure-config resource (no on-disk artifact), so it uses
the generic create/update path. Its only secret is ``secret_ref``,
surfaced to ResourceService so a missing key fails before the DB write and so
deleting a still-cited secret is refused.

Handed the rows it guards, the kind also refuses a direct write that would flag
a second speech-to-text default (spec provider-switching "Keep an independent
speech-to-text default"; ``internal_default_guard``).
"""

from __future__ import annotations

from typing import Any, Protocol

from coffer.application.provider.internal_default_guard import EXCLUSIVE_FLAGS, refusing_hooks
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Kind, Resource


def _provider_secret_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """The profile's API-key ref, probed at register/update time."""
    ref = config.get("secret_ref")
    if isinstance(ref, str) and ref:
        return {"secret_ref": ref}
    return {}


class _Rows(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> list[Resource]: ...


def make_provider_kind(rows: _Rows | None = None) -> Kind:
    """Construct the ``provider`` Kind.

    ``rows`` is the resource table the one-flag rule is checked against — the
    composition root passes its ``ResourceService``. Omitted, the kind has no
    pre-write hooks and the vault's exclusive-flag rule is the only guard left.
    """
    on_register, on_update = refusing_hooks(rows) if rows is not None else (None, None)
    return Kind(
        free_name=True,
        name="provider",
        display_name="Provider",
        config_schema=ProviderConfig,
        secret_ref_extractor=_provider_secret_ref_extractor,
        # spec provider-switching "Keep an independent speech-to-text default":
        # the vault refuses a file that would make a second one.
        exclusive_flags=tuple(EXCLUSIVE_FLAGS),
        # No per-agent scope: a connection reaches the agents its addresses
        # serve (ADR provider-reach-is-what-its-addresses-serve). Its switch is
        # retired: nothing can turn a connection off, but the stored flag stays
        # readable so the startup migration can find the ones that were off
        # and move their agents back to their own login. A later release makes
        # it non-toggleable and deletes that migration.
        supports_scope=False,
        switch_retired=True,
        validate_config=on_register,
        on_update_config=on_update,
    )
