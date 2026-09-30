"""/api/v1/clis/* — the command-line tools managed skills require (spec
skill-manager "Serve required commands on REST, the command line and the
web")."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.skill.cli_requirements import CliRequirementService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.cli_dependencies import get_cli_requirement_service
from coffer.surfaces.http.cli_schemas import (
    CliListOut,
    CliOut,
    cli_list_out,
    cli_out,
)

router = APIRouter(
    prefix="/api/v1/clis",
    tags=["clis"],
    dependencies=[Depends(require_token)],
)


@router.get("", response_model=CliListOut)
async def list_clis(
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliListOut:
    """Every command a managed skill requires, problems first."""
    return cli_list_out(await service.listing())


@router.post("/check", response_model=CliListOut)
async def check_clis(
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliListOut:
    """Probe every required command again."""
    return cli_list_out(await service.check_all())


@router.get("/{command}", response_model=CliOut)
async def get_cli(
    command: str,
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliOut:
    """One required command, with the hand-off prompt when it needs the
    person; 404 ``CLI_NOT_REQUIRED`` when no skill requires it."""
    return cli_out(await service.get(command))


@router.post("/{command}/check", response_model=CliOut)
async def check_cli(
    command: str,
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliOut:
    """Probe one required command again."""
    return cli_out(await service.check(command))
