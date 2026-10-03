"""FastAPI dependency provider for the commands skills require (spec
skill-manager "Serve required commands on REST, the command line and the
web"). Same ``set_*`` / ``get_*`` singleton shape as ``skill_dependencies``."""

from __future__ import annotations

from coffer.application.skill.cli_requirements import CliRequirementService
from coffer.application.skill.cli_tools import CliToolService

_service: CliRequirementService | None = None
_tools: CliToolService | None = None


def set_cli_tool_service(svc: CliToolService | None) -> None:
    global _tools
    _tools = svc


def get_cli_tool_service() -> CliToolService:
    if _tools is None:
        raise RuntimeError("cli tool service not initialised")
    return _tools


def set_cli_requirement_service(svc: CliRequirementService | None) -> None:
    """Called by the composition root once on startup."""
    global _service
    _service = svc


def get_cli_requirement_service_optional() -> CliRequirementService | None:
    return _service


def get_cli_requirement_service() -> CliRequirementService:
    """FastAPI Depends() target."""
    if _service is None:
        raise RuntimeError("cli requirement service not initialised")
    return _service
