"""Composition of the credential check (spec channels "Check credentials before
they are saved"): the platform probe, plus the reader that resolves an existing
channel's stored secret so a replacement can be compared with it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from coffer.application.channel.credential_check import (
    CredentialCheck,
    StoredCredentials,
)
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.errors import CofferError
from coffer.domain.secrets import SecretDestination, channel_destination
from coffer.infrastructure.channel.credential_probe import PlatformCredentialProbe

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

Materialize = Callable[[dict[str, str], SecretDestination], Awaitable[dict[str, str]]]


class _ChannelSecretReader:
    def __init__(self, resources: ResourceService, materialize: Materialize) -> None:
        self._resources = resources
        self._materialize = materialize

    async def read(self, channel_uid: str) -> StoredCredentials | None:
        try:
            resource = await self._resources.get(channel_uid)
            if resource.kind != "channel":
                return None
            parsed = parse_channel_config(dict(resource.config))
            if parsed.channel_type == "telegram":
                dest = channel_destination(resource.uid, resource.name, "telegram")
                token = (await self._materialize({"token": parsed.bot_token_ref}, dest))["token"]
                return StoredCredentials(platform="telegram", bot_token=token)
            return StoredCredentials(platform="seatalk", app_id=parsed.app_id)
        except (CofferError, KeyError, ValueError):
            # Not found, not a valid configuration, or a secret that is withheld
            # or gone: nothing to compare with, which the check reports as unknown.
            return None


def build_credential_check(resources: ResourceService, materialize: Materialize) -> CredentialCheck:
    return CredentialCheck(PlatformCredentialProbe(), _ChannelSecretReader(resources, materialize))
