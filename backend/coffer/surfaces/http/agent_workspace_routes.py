"""/api/v1/agents/{uid}/mcp-entries and /plugins routes (spec agent-registry agent workspace).

MCP entries + plugins in the agent's OWN config files, derived at read time —
nothing is stored. Env/header VALUES never cross HTTP: the listing and the
one-entry read expose key names only (plus which keys look secret-like), and
the one-entry read withholds the value of any other secret-looking key.
Domain errors map centrally via surfaces/http/errors.py; the one exception is
adopt's name-conflict 409, which needs a ``suggested_name`` detail and so
builds the envelope explicitly with :func:`coffer.surfaces.http.errors.error_response`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from coffer.application.agent.mcp_entry_service import McpEntryDetail, ParseErrorInfo
from coffer.application.agent.plugin_views import PluginDetailView, PluginView
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.mcp_entries import McpEntry, masked_extra, secret_env_keys
from coffer.domain.agent.plugin_bundle import PluginComponent
from coffer.domain.agent.plugin_state import MarketplaceInfo
from coffer.domain.errors import ResourceAlreadyExists
from coffer.surfaces.http.agent_dependencies import get_agent_service
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.workspace_dependencies import (
    get_agent_mcp_entry_service,
    get_agent_plugin_service,
)

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class McpEntryOut(BaseModel):
    name: str
    source: str
    transport: Literal["stdio", "http"]
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


class McpEntryFieldOut(BaseModel):
    key: str
    # None when masked: a secret-looking key's value never crosses HTTP.
    value: str | None
    masked: bool


class McpEntryDetailOut(McpEntryOut):
    """One entry in full — the listing's fields plus the file it came from, its
    working directory and every other key it carries (secret-looking ones masked)."""

    path: str
    cwd: str | None
    extra: list[McpEntryFieldOut]


class ParseErrorOut(BaseModel):
    source: str
    path: str
    error: str


class McpEntriesOut(BaseModel):
    items: list[McpEntryOut]
    parse_errors: list[ParseErrorOut]


class McpEntryAdopt(BaseModel):
    source: str | None = None
    new_name: str | None = None
    # Maps secret-looking env/header KEY names to credential refs; the VALUES
    # are encrypted into the credential store server-side, never into the
    # resource config.
    secrets: dict[str, str] | None = None


class AdoptedOut(BaseModel):
    """The resource adoption just created.

    ``uid`` is here because this is the only moment the caller learns the new
    resource exists, and it is the only value that will still address it after
    the user renames it — a client that wants to open what it just adopted has
    to hold this, not the label beside it.
    """

    uid: str
    kind: str
    name: str


class PluginOut(BaseModel):
    id: str
    name: str
    marketplace: str
    enabled: bool
    cache_present: bool
    # Best-effort detail read from the plugin's install dir (Claude only today;
    # null/empty otherwise).
    version: str | None = None
    description: str | None = None
    author: str | None = None
    homepage: str | None = None
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)


class MarketplaceOut(BaseModel):
    name: str
    source_type: str | None
    source: str | None


class PluginsOut(BaseModel):
    items: list[PluginOut]
    marketplaces: list[MarketplaceOut]
    parse_errors: list[ParseErrorOut]
    # Whether in-app uninstall is available for this agent now (capability + CLI
    # presence for CLI-strategy agents). Drives the UI's uninstall affordance.
    can_uninstall: bool = False


class PluginComponentOut(BaseModel):
    name: str
    description: str | None = None


class PluginDetailOut(BaseModel):
    """One plugin's detail page (spec agent-registry "Read one installed plugin's
    detail read-only"): the listing row, where it came from, and what it adds."""

    plugin: PluginOut
    marketplace_source_type: str | None
    marketplace_source: str | None
    install_path: str | None
    can_uninstall: bool
    skills: list[PluginComponentOut]
    commands: list[PluginComponentOut]
    agents: list[PluginComponentOut]
    hooks: list[str]
    mcp_servers: list[str]


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


def _entry_detail_out(d: McpEntryDetail) -> McpEntryDetailOut:
    return McpEntryDetailOut(
        **_entry_out(d.entry).model_dump(),
        path=d.path,
        cwd=d.entry.cwd,
        extra=[
            McpEntryFieldOut(key=f.key, value=f.value, masked=f.masked)
            for f in masked_extra(d.entry.extra)
        ],
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
        version=p.version,
        description=p.description,
        author=p.author,
        homepage=p.homepage,
        skills=list(p.skills),
        commands=list(p.commands),
        mcp_servers=list(p.mcp_servers),
    )


def _marketplace_out(m: MarketplaceInfo) -> MarketplaceOut:
    return MarketplaceOut(name=m.name, source_type=m.source_type, source=m.source)


# ---------------------------------------------------------------------------
# MCP entries
# ---------------------------------------------------------------------------


@router.get("/{uid}/mcp-entries", response_model=McpEntriesOut)
async def list_mcp_entries(
    uid: str,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
) -> McpEntriesOut:
    view = await svc.list_entries(uid)
    return McpEntriesOut(
        items=[_entry_out(e) for e in view.items],
        parse_errors=[_parse_error_out(p) for p in view.parse_errors],
    )


@router.get("/{uid}/mcp-entries/{entry}", response_model=McpEntryDetailOut)
async def get_mcp_entry(
    uid: str,
    entry: str,
    source: str | None = None,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
) -> McpEntryDetailOut:
    return _entry_detail_out(await svc.get_entry(uid, entry, source=source))


@router.delete(
    "/{uid}/mcp-entries/{entry}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_mcp_entry(
    uid: str,
    entry: str,
    source: str | None = None,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.remove_entry(uid, entry, source=source, actor=actor)


@router.post(
    "/{uid}/mcp-entries/{entry}/adopt",
    status_code=status.HTTP_201_CREATED,
    response_model=AdoptedOut,
)
async def adopt_mcp_entry(
    uid: str,
    entry: str,
    body: McpEntryAdopt,
    svc: Any = Depends(get_agent_mcp_entry_service),  # noqa: B008
    agent_svc: Any = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Any:
    try:
        resource = await svc.adopt(
            uid,
            entry,
            source=body.source,
            new_name=body.new_name,
            secrets=body.secrets,
            actor=actor,
        )
    except ResourceAlreadyExists as e:
        # Spec agent-registry "Adopt a direct MCP entry into Coffer": the
        # conflict response carries a suggested alternative
        # name. Derived from the agent's type so it stays stable + readable.
        agent = await agent_svc.get(uid)
        agent_type = AgentConfig.model_validate(agent.config).type.value
        return error_response(e.code, str(e), details={"suggested_name": f"{entry}-{agent_type}"})
    return AdoptedOut(uid=resource.uid, kind=resource.kind, name=resource.name)


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


@router.get("/{uid}/plugins", response_model=PluginsOut)
async def list_plugins(
    uid: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginsOut:
    out = await svc.list_plugins(uid)
    return PluginsOut(
        items=[_plugin_out(p) for p in out.items],
        marketplaces=[_marketplace_out(m) for m in out.marketplaces],
        parse_errors=[_parse_error_out(p) for p in out.parse_errors],
        can_uninstall=out.can_uninstall,
    )


@router.get("/{uid}/plugins/{plugin_id}", response_model=PluginDetailOut)
async def get_plugin(
    uid: str,
    plugin_id: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginDetailOut:
    d: PluginDetailView = await svc.get_plugin(uid, plugin_id)
    c = d.contents

    def comps(items: tuple[PluginComponent, ...]) -> list[PluginComponentOut]:
        return [PluginComponentOut(name=i.name, description=i.description) for i in items]

    return PluginDetailOut(
        plugin=_plugin_out(d.plugin),
        marketplace_source_type=d.marketplace_source_type,
        marketplace_source=d.marketplace_source,
        install_path=d.install_path,
        can_uninstall=d.can_uninstall,
        skills=comps(c.skills) if c else [],
        commands=comps(c.commands) if c else [],
        agents=comps(c.agents) if c else [],
        hooks=list(c.hooks) if c else [],
        mcp_servers=list(c.mcp_servers) if c else [],
    )


@router.patch(
    "/{uid}/plugins/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def patch_plugin(
    uid: str,
    plugin_id: str,
    body: PluginPatch,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.set_enabled(uid, plugin_id, body.enabled, actor=actor)


@router.delete(
    "/{uid}/plugins/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_plugin(
    uid: str,
    plugin_id: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.uninstall(uid, plugin_id, actor=actor)
