"""``provider`` Kind wiring for the composition root (spec provider-switching).

A provider profile is a pure-config resource (no on-disk artifact), so it uses
the generic create/update path. Its only credential is ``credential_ref``,
surfaced to ResourceService so a missing key fails before the DB write and so
deleting a still-cited credential is refused.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.provider.config import ProviderConfig, default_scope_for_protocol
from coffer.domain.resource import Kind


def _provider_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """The profile's API-key ref, probed at register/update time."""
    ref = config.get("credential_ref")
    if isinstance(ref, str) and ref:
        return {"credential_ref": ref}
    return {}


def _provider_default_scope(config: dict[str, Any]) -> list[str]:
    """The scope a brand-new connection starts with: the wire's own default.

    Without this the framework would create the row unscoped, i.e. reaching
    EVERY agent — a widening, not a preservation, of the behaviour the
    connection's own ``compatible_agents`` used to give it (an ollama
    connection reaches no agent at all). The wire is already known at create
    time, so the pre-fill is exact rather than a guess.
    """
    protocol = config.get("protocol")
    return default_scope_for_protocol(str(protocol) if protocol is not None else "")


def make_provider_kind() -> Kind:
    """Construct the ``provider`` Kind."""
    return Kind(
        name="provider",
        display_name="Provider",
        config_schema=ProviderConfig,
        credential_ref_extractor=_provider_credential_ref_extractor,
        # Per-agent scope: a connection's scope names the agents it projects
        # into — the axis this kind used to carry itself, as
        # ``compatible_agents`` inside its config, before the framework grew
        # one (ADR per-agent-resource-scope). The projection seam
        # (``application.provider.targets``) is the enforcement point: the
        # switch, the per-agent key lookup, the import reconcile and the boot
        # self-heal all read it.
        supports_scope=True,
        default_scope=_provider_default_scope,
    )
