"""FastAPI dependency providers for the skill kind (spec skill-manager).

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely.
"""

from __future__ import annotations

from coffer.application.skill.service import SkillService

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
