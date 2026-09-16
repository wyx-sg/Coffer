"""Partial-update path for ``ProviderService`` (spec provider-switching).

``credential_ref`` is immutable — it is the vault address the connection owns,
and moving it is what ``rename_ops`` exists for. ``protocol`` is NOT immutable:
an endpoint that turns out to speak a different wire than the probe guessed is
corrected in place rather than deleted and re-entered, key and all.

But the wire is not inert, and saying "nothing keys off it" (as this module and
``ProviderPatch`` both used to) was wrong in two places that matter:

- ``targets.scoped_targets`` answers ``[]`` for ``Protocol.OLLAMA`` BEFORE the
  resource's scope is consulted, so the wire decides whether a connection can
  cover any agent at all; and
- ``service._AGENT_FOR_WIRE`` is how ``use-builtin <wire>`` finds the agent to
  put back on its own login, so the wire decides which revert reaches it.

Which is why a wire change is REFUSED while the connection is ``is_active``.
Allowing it would strand the projection: a live anthropic connection moved to
``ollama`` loses every target while the ``~/.claude/settings.json`` it already
wrote stays behind, and one moved to ``openai`` stops answering to
``use-builtin anthropic`` while ``use-builtin openai`` goes to Codex instead —
either way nothing left would ever de-project it. De-projecting silently would
be worse than refusing: the user asked to edit a field, not to take their
agents off a gateway. An inactive connection is unaffected — no projection
exists to strand. The re-validate below still enforces the other rule the wire
carries: an ollama connection holds no key.

``is_active`` is read from the STORED config rather than from the patch: the
flip is ``activate`` / ``deactivate``'s business and never travels in a patch.

Which agents a connection projects into is NOT patched here: it is the
framework-level scope on the resource row, edited through the scope surface
every scoped kind shares.

Lives here rather than in ``provider/service.py`` because that module is at its
file-size ceiling; ``ProviderService.update`` stays a thin delegate, mirroring
``rename``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.provider.errors import (
    ProviderCredentialSourceInvalid,
    ProviderProtocolLockedWhileActive,
)
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService, _CuratedModels


async def update(
    service: ProviderService,
    name: str,
    *,
    protocol: Protocol | None = None,
    base_url: str | None = None,
    secret_value: str | None = None,
    models: _CuratedModels | None = None,
    description: str | None = None,
    actor: str = "api",
) -> Resource:
    """Apply a partial update; see the module docstring for what may move."""
    current = await service.get(name)
    config = dict(current.config)
    if protocol is not None and protocol.value != config.get("protocol"):
        # Refused, not de-projected — see the module docstring. Re-sending the
        # wire the connection already has is not a change, so a client that
        # submits a whole form rather than a diff is never told its unchanged
        # dropdown is a conflict.
        if config.get("is_active"):
            raise ProviderProtocolLockedWhileActive(name, str(config.get("protocol")))
        config["protocol"] = protocol.value
    if base_url is not None:
        config["base_url"] = base_url
    if models is not None:
        config["models"] = [m.model_dump(mode="json") for m in models]
    # Re-validate so a bad edit is rejected before the rotation / DB write.
    validated = ProviderConfig.model_validate(config).model_dump(mode="json")
    if secret_value is not None:
        ref = config.get("credential_ref")
        if not ref:
            raise ProviderCredentialSourceInvalid()
        await asyncio.to_thread(service._credentials.set, str(ref), secret_value)
    return await service._resources.update_config(
        service._ref(name), validated, actor, description=description
    )
