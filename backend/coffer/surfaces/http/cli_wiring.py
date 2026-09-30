"""Compose the required-command check (``CliRequirementService``) over the
skill service, the machine's ``PATH`` and the machine's description.

``build_command_probe`` is the seam a test replaces with a fake.
"""

from __future__ import annotations

from functools import cache

from coffer.application.skill.cli_documents import MasterSkillDocuments
from coffer.application.skill.cli_requirements import CliRequirementService, CommandProbePort
from coffer.application.skill.service import SkillService
from coffer.infrastructure.platform.host import machine_label
from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe
from coffer.surfaces.http.cli_dependencies import set_cli_requirement_service


def build_command_probe() -> CommandProbePort:
    return CommandProbe(user_path=UserPath())


def wire_cli_requirements(skill_svc: SkillService) -> CliRequirementService:
    """Build the service and publish it for the routes and the attention list."""
    service = CliRequirementService(
        skills=MasterSkillDocuments(skill_svc),
        probe=build_command_probe(),
        # The OS and architecture do not change while the daemon runs.
        machine=cache(machine_label),
    )
    set_cli_requirement_service(service)
    return service


__all__ = ["build_command_probe", "wire_cli_requirements"]
