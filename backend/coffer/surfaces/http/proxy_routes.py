"""``/api/v1/proxy`` — the local model proxy's management routes (spec
provider-switching "Authenticate each agent to the proxy with its own local
token"; spec daemon "Supervise the model proxy from the daemon").

The token route is what ``coffer proxy token --agent-uid <uid>`` calls — the
command Claude Code's ``apiKeyHelper`` and Codex's provider ``auth`` run. It
returns a LOCAL token that unlocks only the loopback proxy, never a provider
key: no route of the daemon returns a provider key any more (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.proxy_dependencies import ProxyFacade, get_proxy_facade

router = APIRouter(prefix="/api/v1/proxy", tags=["proxy"], dependencies=[Depends(require_token)])


class ProxyStatusOut(BaseModel):
    #: Whether the supervisor sees a live proxy answering its control route.
    running: bool
    pid: int | None
    #: The port the proxy listens on (fixed, from ``daemon-config.json``).
    port: int
    version: str | None
    #: How many times the daemon restarted it after a crash.
    restarts: int
    last_error: str | None
    #: The revision of the state last pushed to it.
    revision: int | None
    #: Consecutive failed attempts to start it (0 while it is up, or idle
    #: because no agent is routed through it).
    consecutive_failures: int
    #: Starting it has failed repeatedly; the daemon retries on a slow backoff.
    failing: bool


class ProxyTokenOut(BaseModel):
    agent_uid: str
    #: The agent's local proxy token — what its key helper prints.
    token: str


class ProxyTokenRotatedOut(BaseModel):
    agent_uid: str
    rotated: bool


class ProxyTokenHintOut(BaseModel):
    """What the Model tab shows of an agent's token: its last four characters,
    never the token."""

    agent_uid: str
    last4: str


async def _known(facade: ProxyFacade, agent_uid: str) -> None:
    if not await facade.agent_exists(agent_uid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such agent")


@router.get("/status", response_model=ProxyStatusOut)
async def proxy_status(facade: ProxyFacade = Depends(get_proxy_facade)) -> ProxyStatusOut:  # noqa: B008
    """The supervised proxy's state, as the daemon last saw it."""
    return ProxyStatusOut(**facade.status())


@router.get("/tokens/{agent_uid}", response_model=ProxyTokenOut)
async def proxy_token(
    agent_uid: str,
    facade: ProxyFacade = Depends(get_proxy_facade),  # noqa: B008
) -> ProxyTokenOut:
    """The agent's local proxy token, minted on first ask. 404 for an agent
    this machine does not have, so a stale helper fails closed."""
    await _known(facade, agent_uid)
    token, minted = await facade.tokens.issue(agent_uid)
    if minted:
        # The proxy learns a token's digest from a state push; a token that was
        # already there is already known, so a plain read (every helper call)
        # pushes nothing.
        await facade.refresh()
    return ProxyTokenOut(agent_uid=agent_uid, token=token)


@router.get("/tokens/{agent_uid}/hint", response_model=ProxyTokenHintOut)
async def proxy_token_hint(
    agent_uid: str,
    facade: ProxyFacade = Depends(get_proxy_facade),  # noqa: B008
) -> ProxyTokenHintOut:
    """The last four characters of the agent's token, minted on first ask."""
    await _known(facade, agent_uid)
    token = await facade.tokens.token_for(agent_uid)
    return ProxyTokenHintOut(agent_uid=agent_uid, last4=token[-4:])


@router.post("/tokens/{agent_uid}/rotate", response_model=ProxyTokenRotatedOut)
async def rotate_proxy_token(
    agent_uid: str,
    facade: ProxyFacade = Depends(get_proxy_facade),  # noqa: B008
) -> ProxyTokenRotatedOut:
    """Replace the agent's token; the old one is refused from the next push,
    which happens before this answers."""
    await _known(facade, agent_uid)
    await facade.tokens.rotate(agent_uid)
    await facade.refresh()
    return ProxyTokenRotatedOut(agent_uid=agent_uid, rotated=True)


__all__ = ["router"]
