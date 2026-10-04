"""DI providers for the local model proxy's management routes (spec
provider-switching "Authenticate each agent to the proxy with its own local
token"; spec daemon "Supervise the model proxy from the daemon")."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from coffer.application.provider.proxy_tokens import ProxyTokenService
from coffer.domain.model_proxy.state import ProxyState


@dataclass(frozen=True)
class ProxyFacade:
    """What the routes reach: tokens, the supervisor's status, and a refresh
    that re-pushes the proxy's state after a token changes."""

    tokens: ProxyTokenService
    status: Callable[[], dict[str, Any]]
    refresh: Callable[[], Awaitable[None]]
    #: The name of the agent with this uid (what its token is kept under), or
    #: None for an agent this machine does not have.
    agent_name: Callable[[str], Awaitable[str | None]]
    #: The state the proxy would be pushed now (what the supervisor pushes).
    state: Callable[[], Awaitable[ProxyState]]


_facade: ProxyFacade | None = None


def set_proxy_facade(facade: ProxyFacade | None) -> None:
    global _facade
    _facade = facade


def get_proxy_facade() -> ProxyFacade:
    if _facade is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="model proxy not wired"
        )
    return _facade


__all__ = ["ProxyFacade", "get_proxy_facade", "set_proxy_facade"]
