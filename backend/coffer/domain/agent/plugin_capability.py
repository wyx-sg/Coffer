"""Plugin-capability value objects for the agent manifest.

Split out of ``descriptor.py`` (which re-exports them) to keep that module
within the size budget. These describe *how* Coffer manages one agent's plugins
— the parse/toggle model, the documented write surface, and how an uninstall is
carried out — so the plugin service dispatches on data, not on agent type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PluginModel(StrEnum):
    """Which plugin parse/toggle/uninstall strategy an agent uses."""

    #: Claude Code — 3 internal/settings files; toggle writes settings only.
    CLAUDE = "claude"
    #: Codex — ``[plugins."<id>"]`` tables in config.toml + a cache dir.
    CODEX = "codex"


class UninstallStrategy(StrEnum):
    """How an agent's plugin uninstall is carried out.

    ``CONFIG_EDIT`` removes the plugin by editing the agent's documented config
    file (and deleting its cache dir) — safe because that file is a Coffer write
    surface. ``CLI`` shells out to the agent's own plugin CLI; used when the
    install state lives in an agent-internal file Coffer must not hand-edit
    (Claude Code's ``installed_plugins.json``), so the agent's CLI owns the
    mutation and Coffer never writes that file.
    """

    CONFIG_EDIT = "config_edit"
    CLI = "cli"


@dataclass(frozen=True)
class PluginCapability:
    """How Coffer manages one agent's plugins (the plugin facet of the manifest).

    Carries enough for the service to dispatch without a type switch: the
    ``model`` strategy discriminator, the allowlist ``config_key`` of the write
    surface (``None`` for list-only agents), and capability flags.
    """

    model: PluginModel
    #: Allowlist key of the file the toggle/uninstall transforms write
    #: (``"settings"`` for Claude, ``"config"`` for the rest; ``None`` =
    #: list-only, no write surface).
    config_key: str | None
    can_toggle: bool = True
    can_uninstall: bool = False
    #: How an uninstall is performed when ``can_uninstall`` is True. Defaults to
    #: editing the documented config surface; Claude uses ``CLI`` so its
    #: internal inventory file is never hand-written.
    uninstall_strategy: UninstallStrategy = UninstallStrategy.CONFIG_EDIT
