"""Plugin-capability value objects for the agent manifest.

Split out of ``descriptor.py`` (which re-exports them) to keep that module
within the size budget. These describe *how* Coffer reads one agent's
plugins — the parse model and the file the state is read from — so the plugin
service dispatches on data, not on agent type. Coffer reads this facet and
never writes it: the toggle and uninstall paths were removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PluginModel(StrEnum):
    """Which plugin parse strategy an agent uses."""

    #: Claude Code — inventory files plus enabled state in ``settings.json``.
    CLAUDE = "claude"
    #: Codex — ``[plugins."<id>"]`` tables in config.toml + a cache dir.
    CODEX = "codex"


@dataclass(frozen=True)
class PluginCapability:
    """How Coffer reads one agent's plugins (the plugin facet of the manifest).

    Carries enough for the service to dispatch without a type switch: the
    ``model`` strategy discriminator and the allowlist ``config_key`` the
    enabled state is read from.
    """

    model: PluginModel
    #: Allowlist key of the file carrying the enabled state
    #: (``"settings"`` for Claude, ``"config"`` for the rest; ``None`` = the
    #: agent exposes no such file).
    config_key: str | None
