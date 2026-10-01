"""Compose the required-command check (``CliRequirementService``) over the
skill service, the MCP servers' launchers (handed in by the composition root,
which may see both kinds), the machine's ``PATH`` and the machine's
description.

``build_command_probe`` is the seam a test replaces with a fake.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache

from coffer.application.skill.cli_documents import MasterSkillDocuments
from coffer.application.skill.cli_requirements import (
    CliRequirementService,
    CommandProbePort,
    McpLaunchersPort,
)
from coffer.application.skill.service import SkillService
from coffer.infrastructure.platform.host import machine_label
from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe
from coffer.surfaces.http.cli_dependencies import set_cli_requirement_service


def build_command_probe() -> CommandProbePort:
    return CommandProbe(user_path=UserPath())


def wire_cli_requirements(
    skill_svc: SkillService,
    servers: McpLaunchersPort | None = None,
    secret_set: Callable[[str], bool] | None = None,
) -> CliRequirementService:
    """Build the service and publish it for the routes and the attention list.

    ``secret_set`` answers whether a secret name is in Coffer's secret store,
    for the secrets skills declare they require."""
    service = CliRequirementService(
        skills=MasterSkillDocuments(skill_svc),
        servers=servers,
        secret_set=secret_set,
        probe=build_command_probe(),
        # The OS and architecture do not change while the daemon runs.
        machine=cache(machine_label),
    )
    set_cli_requirement_service(service)
    return service


__all__ = ["build_command_probe", "wire_cli_requirements"]
