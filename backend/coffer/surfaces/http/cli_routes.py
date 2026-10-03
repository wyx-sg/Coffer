"""/api/v1/clis/* — the command-line tools Coffer knows: required by managed
skills or MCP servers, or added by hand (spec skill-manager "Serve required
commands on REST, the command line and the web", "Declare a command-line tool
without a skill", "Serve required commands on REST, the command line and the web")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.skill.cli_interface import CliInterfaceService
from coffer.application.skill.cli_requirements import CliRequirementService
from coffer.application.skill.cli_tools import CliToolService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.cli_dependencies import (
    get_cli_interface_service,
    get_cli_requirement_service,
    get_cli_tool_service,
)
from coffer.surfaces.http.cli_interface_schemas import CliInterfaceOut, cli_interface_out
from coffer.surfaces.http.cli_schemas import (
    CliAddIn,
    CliEditIn,
    CliListOut,
    CliOut,
    CliPreviewIn,
    CliPreviewOut,
    cli_list_out,
    cli_out,
    cli_preview_out,
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
    """Every command a skill or MCP server requires or the person added by
    hand, problems first."""
    return cli_list_out(await service.listing())


@router.post("/check", response_model=CliListOut)
async def check_clis(
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliListOut:
    """Probe every required command again."""
    return cli_list_out(await service.check_all())


@router.post("", response_model=CliOut, status_code=status.HTTP_201_CREATED)
async def add_cli(
    body: CliAddIn,
    tools: CliToolService = Depends(get_cli_tool_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CliOut:
    """Add a command-line tool by hand, with no skill. 409 ``CLI_TOOL_EXISTS``
    when it was already added; 400 ``CLI_TOOL_INVALID`` for a bad name, path,
    version or login check."""
    view = await tools.add(
        body.command,
        title=body.title,
        description=body.description,
        min_version=body.min_version,
        login_check=body.login_check,
        actor=actor,
    )
    return cli_out(view)


@router.post("/preview", response_model=CliPreviewOut)
async def preview_cli(
    body: CliPreviewIn,
    tools: CliToolService = Depends(get_cli_tool_service),  # noqa: B008
) -> CliPreviewOut:
    """What Coffer finds for a command name or path — where, which version,
    whether it is already added or required — before anything is saved."""
    return cli_preview_out(await tools.preview(body.command))


@router.get("/{command}", response_model=CliOut)
async def get_cli(
    command: str,
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliOut:
    """One command, with the hand-off prompt when it needs the person; 404
    ``CLI_NOT_KNOWN`` when no skill or MCP server requires it and it was not
    added by hand."""
    return cli_out(await service.get(command))


@router.post("/{command}/check", response_model=CliOut)
async def check_cli(
    command: str,
    service: CliRequirementService = Depends(get_cli_requirement_service),  # noqa: B008
) -> CliOut:
    """Probe one required command again."""
    return cli_out(await service.check(command))


@router.patch("/{command}", response_model=CliOut)
async def edit_cli(
    command: str,
    body: CliEditIn,
    tools: CliToolService = Depends(get_cli_tool_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CliOut:
    """Change a tool added by hand; a field left out stays, ``null`` clears it.
    404 ``CLI_TOOL_NOT_DECLARED`` for a tool no one added by hand."""
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    return cli_out(await tools.edit(command, changes, actor=actor))


@router.delete("/{command}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_cli(
    command: str,
    tools: CliToolService = Depends(get_cli_tool_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Drop the hand-added declaration. A skill or MCP server that requires the
    command keeps it listed. 404 ``CLI_TOOL_NOT_DECLARED`` for a tool no one
    added by hand."""
    await tools.remove(command, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{command}/interface", response_model=CliInterfaceOut)
async def get_cli_interface(
    command: str,
    service: CliInterfaceService = Depends(get_cli_interface_service),  # noqa: B008
) -> CliInterfaceOut:
    """The interface read from the tool's help, as kept for this version of
    it. Never runs the tool: ``not_read`` until a POST reads it."""
    return cli_interface_out(await service.get(command))


@router.post("/{command}/interface", response_model=CliInterfaceOut)
async def read_cli_interface(
    command: str,
    service: CliInterfaceService = Depends(get_cli_interface_service),  # noqa: B008
) -> CliInterfaceOut:
    """Run the tool's help — ``--help``, ``-h`` and each subcommand's, nothing
    else — and keep the tree. May take up to 30 seconds."""
    return cli_interface_out(await service.read(command))
