"""Compose the required-command check (``CliRequirementService``) over the
skill service, the MCP servers' launchers (handed in by the composition root,
which may see both kinds), the machine's ``PATH`` and the machine's
description.

``build_command_probe`` and ``build_help_runner`` are the seams a test
replaces with fakes. The tools added by hand are a vault state document; where
one was found on this machine is local state.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache

from coffer.application.audit_service import AuditService
from coffer.application.skill.cli_discovery import HelpRunnerPort
from coffer.application.skill.cli_documents import MasterSkillDocuments
from coffer.application.skill.cli_interface import CliInterfaceService
from coffer.application.skill.cli_requirements import (
    CliRequirementService,
    CommandProbePort,
    McpLaunchersPort,
)
from coffer.application.skill.cli_tools import CliToolService
from coffer.application.skill.service import SkillService
from coffer.infrastructure.platform.host import machine_label
from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.cli_interface_store import LocalInterfaceStore
from coffer.infrastructure.skill.cli_tool_repo import LocalCliPaths, VaultCliToolRepo
from coffer.infrastructure.skill.command_probe import CommandProbe
from coffer.infrastructure.skill.help_runner import HelpRunner
from coffer.surfaces.http.cli_dependencies import (
    set_cli_interface_service,
    set_cli_requirement_service,
    set_cli_tool_service,
)


def build_command_probe() -> CommandProbePort:
    return CommandProbe(user_path=UserPath())


def build_help_runner() -> HelpRunnerPort:
    return HelpRunner(user_path=UserPath())


def wire_cli_requirements(
    skill_svc: SkillService,
    audit: AuditService,
    servers: McpLaunchersPort | None = None,
    secret_set: Callable[[str], bool] | None = None,
) -> CliRequirementService:
    """Build the service and publish it for the routes and the attention list.

    ``secret_set`` answers whether a secret name is in Coffer's secret store,
    for the secrets skills declare they require."""
    probe = build_command_probe()
    declared = VaultCliToolRepo()
    paths = LocalCliPaths()
    service = CliRequirementService(
        skills=MasterSkillDocuments(skill_svc),
        servers=servers,
        declared=declared,
        paths=paths,
        secret_set=secret_set,
        probe=probe,
        # The OS and architecture do not change while the daemon runs.
        machine=cache(machine_label),
    )
    set_cli_requirement_service(service)
    set_cli_tool_service(
        CliToolService(
            requirements=service, declared=declared, paths=paths, probe=probe, audit=audit
        )
    )
    set_cli_interface_service(
        CliInterfaceService(
            requirements=service, runner=build_help_runner(), store=LocalInterfaceStore()
        )
    )
    return service


__all__ = ["build_command_probe", "build_help_runner", "wire_cli_requirements"]
