"""/api/v1/fs/terminal and /api/v1/fs/terminals — agent sessions in a terminal.

Spec daemon "Open an agent session in a terminal" and "List the terminals
installed on this host". The body names what to run (an agent, a session to
resume or a prompt to begin with), never a command line: the daemon builds the
command itself.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict

from coffer.application.fs.terminal_service import TerminalDetectService, TerminalService
from coffer.application.platform_port import PlatformPort
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.vault.home import handoff_dir
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_platform

router = APIRouter(
    prefix="/api/v1/fs",
    tags=["fs"],
    dependencies=[Depends(require_token)],
)


def get_terminal_service(
    platform: PlatformPort = Depends(get_platform),  # noqa: B008
) -> TerminalService:
    """FastAPI Depends() target — stateless, built per-request."""
    return TerminalService(
        platform, default_workspace=default_workspace_dir, handoff_dir=handoff_dir
    )


def get_terminal_detect_service(
    platform: PlatformPort = Depends(get_platform),  # noqa: B008
) -> TerminalDetectService:
    """FastAPI Depends() target — stateless, built per-request."""
    return TerminalDetectService(platform)


class FsTerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal: str | None = None
    agent: str
    cwd: str | None = None
    resume: str | None = None
    prompt: str | None = None


class TerminalOptionOut(BaseModel):
    label: str
    value: str


class FsTerminalsOut(BaseModel):
    terminals: list[TerminalOptionOut]


@router.post("/terminal", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def open_terminal(
    body: FsTerminalRequest,
    svc: TerminalService = Depends(get_terminal_service),  # noqa: B008
) -> Response:
    """Start an agent's session in a terminal window on this host."""
    await asyncio.to_thread(
        svc.open_session,
        terminal=body.terminal,
        agent=body.agent,
        cwd=body.cwd,
        resume=body.resume,
        prompt=body.prompt,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/terminals", response_model=FsTerminalsOut)
async def list_terminals(
    svc: TerminalDetectService = Depends(get_terminal_detect_service),  # noqa: B008
) -> FsTerminalsOut:
    """List the terminals detected on this machine for the preferred-terminal setting."""
    # to_thread: detection does blocking PATH lookups / app-bundle stat calls.
    found = await asyncio.to_thread(svc.list_terminals)
    return FsTerminalsOut(
        terminals=[TerminalOptionOut(label=t.label, value=t.value) for t in found]
    )
