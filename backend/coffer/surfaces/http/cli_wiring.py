"""Compose the required-command check (``CliRequirementService``) over the
skill service, the machine's ``PATH`` and its Homebrew.

``build_command_probe`` and ``build_installer`` are the seams a test replaces
with fakes: nothing under test may run a real ``brew``.
"""

from __future__ import annotations

from coffer.application.audit_service import AuditService
from coffer.application.skill.cli_documents import MasterSkillDocuments
from coffer.application.skill.cli_requirements import (
    CliRequirementService,
    CommandProbePort,
    InstallerPort,
)
from coffer.application.skill.service import SkillService
from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe
from coffer.infrastructure.skill.homebrew import HomebrewInstaller
from coffer.surfaces.http.cli_dependencies import set_cli_requirement_service


def build_command_probe() -> CommandProbePort:
    return CommandProbe(user_path=UserPath())


def build_installer() -> InstallerPort:
    return HomebrewInstaller(user_path=UserPath())


def wire_cli_requirements(skill_svc: SkillService, audit: AuditService) -> CliRequirementService:
    """Build the service and publish it for the routes and the attention list."""
    service = CliRequirementService(
        skills=MasterSkillDocuments(skill_svc),
        probe=build_command_probe(),
        installer=build_installer(),
        audit=audit,
    )
    set_cli_requirement_service(service)
    return service


__all__ = ["build_command_probe", "build_installer", "wire_cli_requirements"]
