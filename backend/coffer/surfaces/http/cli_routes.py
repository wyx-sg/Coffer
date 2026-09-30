"""/api/v1/clis/* — the command-line tools managed skills require (spec
skill-manager "Cover required commands on REST, the command line and the
web")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from coffer.application.skill.cli_requirements import CliRequirementService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.cli_dependencies import get_cli_requirement_service
from coffer.surfaces.http.cli_schemas import (
    CliInstallIn,
    CliInstallOut,
    CliListOut,
    CliOut,
    cli_install_out,
    cli_list_out,
    cli_out,
)
from coffer.surfaces.http.dependencies import get_actor

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
    """One required command; 404 ``CLI_NOT_REQUIRED`` when no skill requires it."""
    return cli_out(await service.get(command))


@router.post("/{command}/check", response_model=CliOut)
async def check_cli(
    command: str,
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliOut:
    """Probe one required command again."""
    return cli_out(await service.check(command))


@router.post(
    "/{command}/install", response_model=CliInstallOut, status_code=status.HTTP_202_ACCEPTED
)
async def install_cli(
    command: str,
    body: CliInstallIn,
    actor: str = Depends(get_actor),
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliInstallOut:
    """Start ``brew install|upgrade <formula>``; refused unless the command is
    missing or outdated, ``formula`` is the declared one and Homebrew is found."""
    return cli_install_out(await service.start_install(command, body.formula, actor=actor))


@router.get("/{command}/install", response_model=CliInstallOut)
async def get_cli_install(
    command: str,
    since: int = Query(default=0, ge=0, description="Only output lines from this number on."),
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliInstallOut:
    """The latest install job for the command: its state, exit code and output."""
    return cli_install_out(service.install_status(command, since))
