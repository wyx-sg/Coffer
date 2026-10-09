"""A provider connection's key goes only where a person approved it.

The key-bearing destination of a provider connection is its **base URL**: the
local model proxy injects the key into requests to that URL, and Coffer's own
engine sends it there too. Pointing an existing key at a new base URL is
sending the secret somewhere new, so it waits for approval in the desktop app
(spec secret "Hold a secret for a new destination until a person approves
it"); until then the connection is no member of the proxy's state and the
engine cannot use it. Replacing the key itself is an ordinary write and takes
effect at once ("Store a secret through the API").

The boundary is the secret package's ``SecretBoundary``, reached through
the port below and set by the composition root; ``None`` (a test-built
service) gates nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

from coffer.domain.provider.config import ProviderConfig
from coffer.domain.secrets import SecretDestination

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService

KIND = "provider"
SLOT = "key"


class ProviderSecretBoundary(Protocol):
    def require(self, dest: SecretDestination, refs: Mapping[str, str]) -> None: ...


def provider_destination(uid: str, name: str, cfg: ProviderConfig) -> SecretDestination:
    # The protocol decides which header carries the key (``Authorization`` or
    # ``x-api-key``), so it is part of what a person approves (spec secret "Fix a
    # secret's placement by its destination's definition").
    target = f"model api {cfg.base_url} as {cfg.protocol.value}"
    # A second, Anthropic address receives the key too, so it is part of what
    # is approved: adding or moving it waits for approval like a new base URL.
    if cfg.anthropic_base_url and cfg.anthropic_base_url != cfg.base_url:
        target += f"; {cfg.anthropic_base_url} as anthropic"
    return SecretDestination(kind=KIND, uid=uid, target=target, label=name)


async def require_key(service: ProviderService, uid: str, name: str, cfg: ProviderConfig) -> None:
    """Raise ``SecretBindingPending`` unless this connection's key may go to its URL."""
    boundary = service._boundary
    if boundary is None or cfg.secret_ref is None:
        return
    dest = provider_destination(uid, name, cfg)
    await asyncio.to_thread(boundary.require, dest, {SLOT: cfg.secret_ref})


async def write_key(service: ProviderService, ref: str, value: str, *, actor: str) -> None:
    """Store a key, replacing the old one at once: whoever supplies it already has it."""
    await asyncio.to_thread(service._secrets.set, ref, value)
