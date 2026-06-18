"""Value objects for a plugin's on-disk detail + bundled components.

Pure data. The filesystem reading that populates these lives in
``infrastructure/agent/plugin_bundle.py`` and is injected into
``AgentPluginService`` (via a Protocol), so the application layer stays
I/O-free and the listing degrades gracefully when a plugin package is
incomplete (missing manifest or bundle dirs → ``None`` / empty tuples).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginDetail:
    """A plugin's manifest metadata plus the components it bundles.

    Every field is best-effort: ``version``/``description``/``author``/
    ``homepage`` come from the plugin manifest (``.claude-plugin/plugin.json``
    or ``.codex-plugin/plugin.json``; any field may be absent), and the three
    component tuples enumerate the plugin's ``skills/`` subfolders, ``commands/``
    markdown files, and ``.mcp.json`` server names respectively.
    """

    version: str | None = None
    description: str | None = None
    author: str | None = None
    homepage: str | None = None
    skills: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()
