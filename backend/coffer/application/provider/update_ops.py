"""Partial-update path for ``ProviderService`` (spec provider-switching).

``secret_ref`` may be re-pointed to ANOTHER stored secret (the "use another
stored secret" half of Replace key); a new value for the current secret is
``secret_value``, and the two never travel together. A connection without a key
(a local runtime) takes neither. ``protocol`` is NOT immutable:
an endpoint that turns out to speak a different wire than the probe guessed is
corrected in place rather than deleted and re-entered, key and all.

But the wire is not inert: it decides how Coffer projects the connection into
an agent's native config. So a wire change is REFUSED while an agent runs on the
connection. Allowing it would leave the native file Coffer already wrote
speaking the old wire, and de-projecting silently would be worse than refusing:
the user asked to edit a field, not to take their agents off a gateway. A
connection no agent runs on is unaffected — no projection exists to strand.

The ``ollama`` protocol is retired: moving a connection onto it is refused
(``ProviderProtocolRetired``); a stored one keeps its value and stays editable.

"An agent runs on it" is read from the agents' own records
(``AgentConfig.connection_uid``), never from the patch: the switch is
``activate`` / ``deactivate``'s business.

Which agents a connection projects into is NOT patched here: it is the
framework-level scope on the resource row, edited through the scope surface
every scoped kind shares.

Lives here rather than in ``provider/service.py`` because that module is at its
file-size ceiling; ``ProviderService.update`` stays a thin delegate, mirroring
how ``ResourceService`` delegates its own long paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.provider.secret_gate import write_key
from coffer.domain.agent.config import AgentConfig
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.provider.errors import (
    ProviderProtocolLockedWhileActive,
    ProviderProtocolRetired,
    ProviderSecretSourceInvalid,
)
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService, _CuratedModels


def _agents_running_on(uid: str, agents: list[Resource]) -> list[str]:
    """The types of the agents whose record names connection ``uid``."""
    running: list[str] = []
    for row in agents:
        try:
            cfg = AgentConfig.model_validate(row.config)
        except ValueError:
            continue
        if cfg.connection_uid == uid:
            running.append(cfg.type.value)
    return running


async def update(
    service: ProviderService,
    uid: str,
    *,
    protocol: Protocol | None = None,
    base_url: str | None = None,
    anthropic_base_url: str | None = None,
    secret_value: str | None = None,
    secret_ref: str | None = None,
    models: _CuratedModels | None = None,
    description: str | None = None,
    actor: str = "api",
) -> Resource:
    """Apply a partial update; see the module docstring for what may move."""
    if secret_ref is not None and secret_value is not None:
        raise ProviderSecretSourceInvalid()
    current = await service.get(uid)
    config = dict(current.config)
    if secret_ref is not None:
        if not config.get("secret_ref"):
            raise ProviderSecretSourceInvalid()
        # ``update_config`` probes the new ref (``SecretMissing`` when nothing
        # is stored there) and ``settle_bindings`` holds it for approval.
        config["secret_ref"] = secret_ref
    # Re-sending the stored wire is not a move, so a connection that already
    # holds the retired value can still be edited.
    if protocol is Protocol.OLLAMA and config.get("protocol") != protocol.value:
        raise ProviderProtocolRetired()
    if protocol is not None and protocol.value != config.get("protocol"):
        # Refused, not de-projected — see the module docstring. Re-sending the
        # wire the connection already has is not a change, so a client that
        # submits a whole form rather than a diff is never told its unchanged
        # dropdown is a conflict.
        running = _agents_running_on(uid, await service._agents.list())
        if running:
            # The connection's NAME in the error, because the message is read
            # by a person looking at a form they just submitted; the uid it was
            # addressed by would tell them nothing.
            raise ProviderProtocolLockedWhileActive(
                current.name, str(config.get("protocol")), running
            )
        config["protocol"] = protocol.value
    if base_url is not None:
        config["base_url"] = base_url
    # ``""`` removes the second address; ``None`` leaves it as it is.
    if anthropic_base_url is not None:
        config["anthropic_base_url"] = anthropic_base_url or None
    if models is not None:
        config["models"] = [m.model_dump(mode="json") for m in models]
    # Re-validate so a bad edit is rejected before the rotation / DB write.
    validated = ProviderConfig.model_validate(config).model_dump(mode="json")
    if secret_value is not None:
        ref = config.get("secret_ref")
        if not ref:
            raise ProviderSecretSourceInvalid()
        # A key some approved destination receives is replaced only after a
        # person approves it in the desktop app (``secret_gate``).
        await write_key(service, str(ref), secret_value, actor=actor)
    return await service._resources.update_config(uid, validated, actor, description=description)
