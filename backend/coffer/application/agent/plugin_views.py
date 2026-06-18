"""Plugin listing value objects + the detail-reader port.

Split out of ``plugin_service.py`` to keep that module within the size budget.
These are the shapes :class:`AgentPluginService` returns and the Protocol it
depends on to read a plugin's on-disk detail (implemented by
``infrastructure.agent.plugin_bundle.FsPluginDetailReader``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.mcp_entry_service import ParseErrorInfo
from coffer.domain.agent.plugin_bundle import PluginDetail
from coffer.domain.agent.plugin_state import MarketplaceInfo


class PluginDetailReader(Protocol):
    """Reads a plugin's manifest + bundled components from its install path.

    Implemented by ``infrastructure.agent.plugin_bundle.FsPluginDetailReader``
    and injected so the application layer never touches the filesystem. Returns
    ``None`` when the path is empty/missing — the listing then omits detail for
    that plugin rather than failing.
    """

    def read(self, install_path: str) -> PluginDetail | None: ...


class PluginCliRunner(Protocol):
    """Shells out to an agent's own plugin CLI for CLI-mediated uninstall.

    Implemented by ``infrastructure.agent.plugin_cli.ClaudePluginCli`` and
    injected so the application layer never spawns subprocesses. ``available``
    reports whether the CLI is on PATH (the listing gates ``can_uninstall`` on
    it); ``uninstall`` runs the command and raises on failure.
    """

    def available(self) -> bool: ...

    def uninstall(self, plugin_id: str) -> None: ...


@dataclass(frozen=True)
class PluginView:
    """One plugin as seen by API consumers.

    The fields below ``cache_present`` are best-effort detail read from the
    plugin's install dir (Claude only today); they stay ``None`` / empty for
    agents or plugins without a readable package.
    """

    id: str
    name: str
    marketplace: str
    enabled: bool
    cache_present: bool
    version: str | None = None
    description: str | None = None
    author: str | None = None
    homepage: str | None = None
    skills: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginsOut:
    """Plugin listing response."""

    items: list[PluginView]
    marketplaces: list[MarketplaceInfo]
    parse_errors: list[ParseErrorInfo]
    #: Whether in-app uninstall is available for this agent right now — the
    #: capability flag AND (for CLI-strategy agents) the CLI being on PATH. The
    #: UI shows the uninstall button on this, not the agent type.
    can_uninstall: bool = False
