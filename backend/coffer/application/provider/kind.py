"""``provider`` Kind wiring for the composition root (spec provider-switching).

A provider profile is a pure-config resource (no on-disk artifact), so it uses
the generic create/update path. Its only credential is ``credential_ref``,
surfaced to ResourceService so a missing key fails before the DB write and so
deleting a still-cited credential is refused.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.provider.config import ProviderConfig, starts_dormant
from coffer.domain.resource import Kind
from coffer.domain.scope import Scope


def _provider_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """The profile's API-key ref, probed at register/update time."""
    ref = config.get("credential_ref")
    if isinstance(ref, str) and ref:
        return {"credential_ref": ref}
    return {}


def _provider_default_scope(config: dict[str, Any]) -> Scope | None:
    """The scope a brand-new connection starts with: dormant, or unscoped.

    The hook is a pure function of the CONFIG — the framework calls it inside
    ``register`` with nothing but the validated dict — so it cannot name an
    agent at all now that a scope holds agent uids
    (ADR resource-identity-is-an-immutable-uid). It does not need to:

    - a keyless (``ollama``) connection starts ``Scope(agents=[])``, dormant,
      because the framework's own default for an unset scope — every agent —
      would advertise a reach a connection with no key can never have; and
    - every other wire starts ``None``, unscoped. That is not a widening of the
      explicit ``[claude_code, codex]`` list it replaces: that list named every
      agent type Coffer supports, which is what "unscoped" means, and unlike
      the list it goes on covering an agent the user registers tomorrow instead
      of quietly excluding it.
    """
    protocol = config.get("protocol")
    if starts_dormant(str(protocol) if protocol is not None else ""):
        return Scope(agents=[])
    return None


def make_provider_kind() -> Kind:
    """Construct the ``provider`` Kind."""
    return Kind(
        name="provider",
        display_name="Provider",
        config_schema=ProviderConfig,
        credential_ref_extractor=_provider_credential_ref_extractor,
        # Per-agent scope: a connection's scope names the agents it projects
        # into — the reach this kind used to carry itself, as
        # ``compatible_agents`` inside its config, before the framework grew
        # one (ADR per-agent-resource-scope). The projection seam
        # (``application.provider.targets``) is the enforcement point: the
        # switch, the per-agent key lookup, the import reconcile and the boot
        # self-heal all read it.
        supports_scope=True,
        default_scope=_provider_default_scope,
    )
