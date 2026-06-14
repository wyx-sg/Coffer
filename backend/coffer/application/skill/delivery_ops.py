"""Skill-delivery-mode helpers for SkillService (spec 005).

Extracted to keep ``service.py`` under the file-size limit. Like
``binding_ops`` / ``lifecycle_ops`` these are free functions that take the
SkillService instance and reach into its (private) attributes — conceptually
private to the skill subpackage.

Two concerns live here:

- **Mode resolution** — which delivery mode an agent uses, read through the
  injected resolver as a plain ``str`` (Contract 5: this layer never imports
  the descriptor's ``SkillDeliveryMode`` enum), and whether that mode is
  *folder-style* (realised as folders on disk).
- **External-dir registration** (EXTERNAL_DIR — Hermes) — folder-deliver into a
  Coffer-owned directory the agent scans and register that directory in the
  agent's own config file. The *where/how* is resolved at the composition root
  and handed in as an ``ExternalDirRegistration``; these helpers only apply it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.skill.external_dir import ExternalDirRegistration

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService
    from coffer.domain.resource import Resource

# Delivery modes that realise a skill as a folder on disk (symlink/copy). Both
# the agent's own ``<config_dir>/skills`` (FOLDER) and a Coffer-owned external
# directory the agent scans (EXTERNAL_DIR) are folder-style: the difference is
# only the target dir (resolved by the injected skill-dir resolver) plus, for
# EXTERNAL_DIR, registering that dir in the agent's config. Compared as literals
# (not enum imports) to keep Contract 5 — this layer only sees resolved strings.
FOLDER_DELIVERY = "folder"
EXTERNAL_DIR_DELIVERY = "external_dir"
_FOLDER_STYLE_DELIVERY = frozenset({FOLDER_DELIVERY, EXTERNAL_DIR_DELIVERY})


def resolve_agent_skill_delivery(service: SkillService, agent: Resource) -> str:
    """The agent's skill-delivery mode value (e.g. ``"folder"``).

    Unwired contexts default to the folder model so existing construction sites
    and tests keep delivering via symlink. Returned as a plain string.
    """
    if service._agent_skill_delivery_resolver is None:
        return FOLDER_DELIVERY
    return service._agent_skill_delivery_resolver(agent)


def delivers_skill_folders(service: SkillService, agent: Resource) -> bool:
    """True for delivery modes realised as folders on disk: FOLDER (the agent's
    own ``skills`` dir) and EXTERNAL_DIR (a Coffer-owned dir the agent scans).
    Non-folder modes (e.g. Cursor's ``rules_mdc``) return False and are gated
    out of delivery."""
    return resolve_agent_skill_delivery(service, agent) in _FOLDER_STYLE_DELIVERY


def resolve_external_registration(
    service: SkillService, agent: Resource
) -> ExternalDirRegistration | None:
    """The agent's external-dir registration (EXTERNAL_DIR mode) or None."""
    if service._agent_external_registration_resolver is None:
        return None
    return service._agent_external_registration_resolver(agent)


async def reconcile_external_registration(service: SkillService, agent: Resource) -> None:
    """Keep the agent's external skill dir registered iff it has ≥1 enabled
    binding; deregister once the last one is removed. No-op for non-external
    agents or an unwired registrar."""
    reg = resolve_external_registration(service, agent)
    if reg is None or service._external_dir_registrar is None:
        return
    bindings = await service._bindings.list_for_agent(agent.id)
    if any(b.enabled for b in bindings):
        service._external_dir_registrar.register(reg)
    else:
        service._external_dir_registrar.deregister(reg)


def deregister_external(service: SkillService, agent: Resource) -> None:
    """Unconditionally deregister the agent's external skill dir — used when the
    agent itself is being deleted, where binding rows are about to go."""
    reg = resolve_external_registration(service, agent)
    if reg is None or service._external_dir_registrar is None:
        return
    service._external_dir_registrar.deregister(reg)
