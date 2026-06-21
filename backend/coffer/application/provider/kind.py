"""``provider`` Kind wiring for the composition root (spec 011).

A provider profile is a pure-config resource (no on-disk artifact), so it uses
the generic create/update path. Its only credential is ``credential_ref``,
surfaced to ResourceService so a missing key fails before the DB write and so
deleting a still-cited credential is refused.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Kind


def _provider_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """The profile's API-key ref, probed at register/update time."""
    ref = config.get("credential_ref")
    if isinstance(ref, str) and ref:
        return {"credential_ref": ref}
    return {}


def make_provider_kind() -> Kind:
    """Construct the ``provider`` Kind."""
    return Kind(
        name="provider",
        display_name="Provider",
        config_schema=ProviderConfig,
        credential_ref_extractor=_provider_credential_ref_extractor,
    )
