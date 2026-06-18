"""Uninstall mechanics for :class:`AgentPluginService`, split out for file size.

Two free functions the service delegates to: the CLI-mediated path (Claude —
shell out to its own ``plugin uninstall`` so Coffer never hand-writes the
agent's internal inventory) and the Codex config-edit path (remove the entry
from ``config.toml`` + delete the cache dir). They take their collaborators
explicitly so the service class stays within the size budget.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.plugin_views import PluginCliRunner
from coffer.application.audit_service import AuditService
from coffer.domain.agent.plugin_state import remove_codex_entry
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef
from coffer.domain.workspace_errors import PluginNotFound, PluginUninstallUnsupported

_UNINSTALLED = AuditEventType.AGENT_PLUGIN_UNINSTALLED.value


async def uninstall_via_cli(
    *,
    cli_runner: PluginCliRunner | None,
    audit: AuditService,
    agent_type: str,
    name: str,
    plugin_id: str,
    actor: str,
) -> None:
    """Delegate uninstall to the agent's own plugin CLI (Claude).

    Runs off the event loop (the subprocess can take seconds). A missing CLI
    surfaces as ``PluginUninstallUnsupported`` (the listing already hides the
    button in that case); a non-zero exit surfaces as ``PluginUninstallFailed``
    from the runner, with the CLI's own message.
    """
    if cli_runner is None or not cli_runner.available():
        raise PluginUninstallUnsupported(agent_type)
    await asyncio.to_thread(cli_runner.uninstall, plugin_id)
    await audit.record(
        _UNINSTALLED,
        ref=ResourceRef("agent", name),
        actor=actor,
        details={"plugin": plugin_id, "cache_removed": True, "via": "cli"},
    )


async def uninstall_codex(
    *,
    store: ConfigFileStorePort,
    audit: AuditService,
    dir_exists: Callable[[pathlib.Path], bool],
    rmtree: Callable[[pathlib.Path], None],
    name: str,
    plugin_id: str,
    spec_path: pathlib.Path,
    cfg_dir: pathlib.Path,
    actor: str,
) -> None:
    """Remove a Codex plugin: drop its ``config.toml`` entry, then its cache dir."""
    text = store.read_text(spec_path)
    if text is None:
        raise PluginNotFound(plugin_id)
    # remove_codex_entry raises PluginNotFound if not present.
    store.write_text_atomic(spec_path, remove_codex_entry(text, plugin_id))

    # plugin_id = "<name>@<marketplace>"; split on the last '@'.
    if "@" in plugin_id:
        at = plugin_id.rfind("@")
        plugin_name, marketplace = plugin_id[:at], plugin_id[at + 1 :]
    else:
        plugin_name, marketplace = plugin_id, ""

    cache_dir = cfg_dir / "plugins" / "cache" / marketplace / plugin_name
    cache_removed = dir_exists(cache_dir)
    # Audit before the cache cleanup: the config entry (source of truth) is
    # already removed, so the event must survive an rmtree failure.
    await audit.record(
        _UNINSTALLED,
        ref=ResourceRef("agent", name),
        actor=actor,
        details={"plugin": plugin_id, "cache_removed": cache_removed},
    )
    if cache_removed:
        rmtree(cache_dir)
