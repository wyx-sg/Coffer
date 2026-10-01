"""FastAPI dependency providers for the skill kind (spec skill-manager).

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.application.skill.service import SkillService
from coffer.application.skill.source_service import SkillSourceService

_skill_service: SkillService | None = None


def set_skill_service(svc: SkillService) -> None:
    """Called by the composition root once on startup."""
    global _skill_service
    _skill_service = svc


def get_skill_service() -> SkillService:
    """FastAPI Depends() target."""
    if _skill_service is None:
        raise RuntimeError("skill service not initialised")
    return _skill_service


_skill_source_service: SkillSourceService | None = None


def set_skill_source_service(svc: SkillSourceService | None) -> None:
    """Called by the composition root once on startup (``skill_source_wiring``)."""
    global _skill_source_service
    _skill_source_service = svc


def get_skill_source_service() -> SkillSourceService:
    """FastAPI Depends() target for the skill-source routes."""
    if _skill_source_service is None:
        raise RuntimeError("skill source service not initialised")
    return _skill_source_service


def get_optional_skill_source_service() -> SkillSourceService | None:
    """For the read model: a graph built without sources still lists skills."""
    return _skill_source_service


_skill_secret_presence: Callable[[str], bool] | None = None


def set_skill_secret_presence(secret_set: Callable[[str], bool] | None) -> None:
    """Called by the composition root once on startup: whether a secret NAME
    is in Coffer's secret store (never its value), for the secrets a skill's
    SKILL.md declares it requires."""
    global _skill_secret_presence
    _skill_secret_presence = secret_set


def get_skill_secret_presence() -> Callable[[str], bool] | None:
    """For the read model; ``None`` in a graph built without the secret store."""
    return _skill_secret_presence
