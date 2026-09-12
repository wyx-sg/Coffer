"""Partial-update path for ``ProviderService`` (spec provider-switching).

``credential_ref`` is immutable — it is the vault address the connection owns,
and moving it is what ``rename_ops`` exists for. ``protocol`` is NOT immutable:
nothing keys off the wire (projection targets come from ``compatible_agents``,
see ``projector``), so an endpoint that turns out to speak a different wire
than the probe guessed is corrected in place rather than deleted and
re-entered, key and all. The re-validate below enforces the one rule the wire
does carry: an ollama connection holds no key and projects nowhere.

Lives here rather than in ``provider/service.py`` because that module is at its
file-size ceiling; ``ProviderService.update`` stays a thin delegate, mirroring
``rename``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.provider.errors import ProviderCredentialSourceInvalid
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService, _AgentTypes, _CuratedModels


async def update(
    service: ProviderService,
    name: str,
    *,
    protocol: Protocol | None = None,
    base_url: str | None = None,
    secret_value: str | None = None,
    compatible_agents: _AgentTypes | None = None,
    models: _CuratedModels | None = None,
    description: str | None = None,
    actor: str = "api",
) -> Resource:
    """Apply a partial update; see the module docstring for what may move."""
    current = await service.get(name)
    config = dict(current.config)
    if protocol is not None:
        config["protocol"] = protocol.value
    if base_url is not None:
        config["base_url"] = base_url
    if compatible_agents is not None:
        config["compatible_agents"] = [a.value for a in compatible_agents]
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
