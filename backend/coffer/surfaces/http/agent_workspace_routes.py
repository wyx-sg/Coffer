"""/api/v1/agents/{name}/mcp-entries and /plugins routes (spec 004 agent workspace).

MCP entries + plugins in the agent's OWN config files, derived at read time —
nothing is stored. Env/header VALUES never cross HTTP: listings expose key
names only (plus which keys look secret-like). Domain errors map centrally via
surfaces/http/errors.py; the one exception is adopt's name-conflict 409, which
needs a ``suggested_name`` detail and so builds the envelope explicitly with
:func:`coffer.surfaces.http.errors.error_response`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from coffer.application.agent.mcp_entry_service import ParseErrorInfo
from coffer.application.agent.plugin_service import PluginView
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.mcp_entries import McpEntry, secret_env_keys
from coffer.domain.agent.plugin_state import MarketplaceInfo
from coffer.domain.errors import ResourceAlreadyExists
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.dependencies import (
    get_agent_mcp_entry_service,
    get_agent_plugin_service,
    get_agent_service,
)
from coffer.surfaces.http.errors import error_response

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class McpEntryOut(BaseModel):
    name: str
    source: str
    transport: str
    command: str | None
    args: list[str]
    # KEY NAMES ONLY — env/header values may carry secrets and never cross HTTP.
    env_keys: list[str]
    secret_keys: list[str]
    url: str | None
    header_keys: list[str]
    enabled: bool | None
    is_coffer: bool
    matches_resource: str | None


class ParseErrorOut(BaseModel):
    source: str
    path: str
    error: str


class McpEntriesOut(BaseModel):
    items: list[McpEntryOut]
    parse_errors: list[ParseErrorOut]


class McpEntryPatch(BaseModel):
    # No `source` field: toggling is Codex-only and Codex has a single MCP
    # source file, so there is never anything to disambiguate.
    enabled: bool


class McpEntryAdopt(BaseModel):
    source: str | None = None
    new_name: str | None = None
    # Maps secret-looking env/header KEY names to keychain refs; the VALUES go
    # into the OS keychain server-side, never into the resource config.
    secrets: dict[str, str] | None = None


class AdoptedOut(BaseModel):
    kind: str
    name: str


class PluginOut(BaseModel):
    id: str
    name: str
    marketplace: str
    enabled: bool
    cache_present: bool


class MarketplaceOut(BaseModel):
    name: str
    source_type: str | None
    source: str | None


class PluginsOut_(BaseModel):  # noqa: N801 — avoids clashing with the service dataclass
    items: list[PluginOut]
    marketplaces: list[MarketplaceOut]
    parse_errors: list[ParseErrorOut]


class PluginPatch(BaseModel):
    enabled: bool


def _entry_out(e: McpEntry) -> McpEntryOut:
    return McpEntryOut(
        name=e.name,
        source=e.source,
        transport=e.transport,
        command=e.command,
        args=list(e.args),
        env_keys=sorted(e.env),
        secret_keys=secret_env_keys({**e.env, **e.headers}),
        url=e.url,
        header_keys=sorted(e.headers),
        enabled=e.enabled,
        is_coffer=e.is_coffer,
        matches_resource=e.matches_resource,
    )


def _parse_error_out(p: ParseErrorInfo) -> ParseErrorOut:
    return ParseErrorOut(source=p.source, path=p.path, error=p.error)


def _plugin_out(p: PluginView) -> PluginOut:
    return PluginOut(
        id=p.id,
        name=p.name,
        marketplace=p.marketplace,
        enabled=p.enabled,
        cache_present=p.cache_present,
    )


def _marketplace_out(m: MarketplaceInfo) -> MarketplaceOut:
    return MarketplaceOut(name=m.name, source_type=m.source_type, source=m.source)


# ---------------------------------------------------------------------------
# MCP entries
# ---------------------------------------------------------------------------


@router.get("/{name}/mcp-entries", response_model=McpEntriesOut)
async def list_mcp_entries(
    name: str,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
) -> McpEntriesOut:
    view = await svc.list_entries(name)
    return McpEntriesOut(
        items=[_entry_out(e) for e in view.items],
        parse_errors=[_parse_error_out(p) for p in view.parse_errors],
    )


@router.patch(
    "/{name}/mcp-entries/{entry}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def patch_mcp_entry(
    name: str,
    entry: str,
    body: McpEntryPatch,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.set_enabled(name, entry, body.enabled, actor=actor)


@router.delete(
    "/{name}/mcp-entries/{entry}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_mcp_entry(
    name: str,
    entry: str,
    source: str | None = None,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.remove_entry(name, entry, source=source, actor=actor)


@router.post(
    "/{name}/mcp-entries/{entry}/adopt",
    status_code=status.HTTP_201_CREATED,
    response_model=AdoptedOut,
)
async def adopt_mcp_entry(
    name: str,
    entry: str,
    body: McpEntryAdopt,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
    agent_svc: Any = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Any:
    try:
        resource = await svc.adopt(
            name,
            entry,
            source=body.source,
            new_name=body.new_name,
            secrets=body.secrets,
            actor=actor,
        )
    except ResourceAlreadyExists as e:
        # Spec FR-028: the conflict response carries a suggested alternative
        # name. Derived from the agent's type so it stays stable + readable.
        agent = await agent_svc.get(name)
        agent_type = AgentConfig.model_validate(agent.config).type.value
        return error_response(e.code, str(e), details={"suggested_name": f"{entry}-{agent_type}"})
    return AdoptedOut(kind=resource.kind, name=resource.name)


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


@router.get("/{name}/plugins", response_model=PluginsOut_)
async def list_plugins(
    name: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginsOut_:
    out = await svc.list_plugins(name)
    return PluginsOut_(
        items=[_plugin_out(p) for p in out.items],
        marketplaces=[_marketplace_out(m) for m in out.marketplaces],
        parse_errors=[_parse_error_out(p) for p in out.parse_errors],
    )


@router.patch(
    "/{name}/plugins/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def patch_plugin(
    name: str,
    plugin_id: str,
    body: PluginPatch,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.set_enabled(name, plugin_id, body.enabled, actor=actor)


@router.delete(
    "/{name}/plugins/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_plugin(
    name: str,
    plugin_id: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.uninstall(name, plugin_id, actor=actor)
