"""CLI-mediated plugin uninstall for Claude Code.

Claude Code records a plugin's installed state in an internal file
(``~/.claude/plugins/installed_plugins.json``) that Coffer treats as read-only —
hand-editing it risks corrupting Claude's plugin state. Instead, uninstall is
delegated to Claude's own ``claude plugin uninstall <id>`` command, which owns
that state (and removes the cache dir). This adapter implements the
application-layer ``PluginCliRunner`` Protocol so the service never spawns
subprocesses itself.

``available()`` gates the in-app uninstall affordance on the CLI being present;
when it is not, the UI keeps the "use the CLI yourself" hint instead.
"""

from __future__ import annotations

import shutil
import subprocess

from coffer.domain.workspace_errors import PluginUninstallFailed

# Bound the subprocess so a hung CLI can't wedge the request handler.
_UNINSTALL_TIMEOUT_S = 120


class ClaudePluginCli:
    """Runs ``claude plugin uninstall`` for CLI-strategy (Claude) uninstall."""

    def __init__(self, executable: str = "claude") -> None:
        self._executable = executable

    def available(self) -> bool:
        return shutil.which(self._executable) is not None

    def uninstall(self, plugin_id: str) -> None:
        """Run ``claude plugin uninstall <plugin_id>``.

        Raises :class:`PluginUninstallFailed` if the CLI is missing, exits
        non-zero, or times out — the service maps that to an actionable error
        rather than leaving the user with a silent no-op.
        """
        if not self.available():
            raise PluginUninstallFailed(plugin_id, "the `claude` CLI is not on PATH")
        try:
            proc = subprocess.run(
                [self._executable, "plugin", "uninstall", plugin_id],
                capture_output=True,
                text=True,
                timeout=_UNINSTALL_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise PluginUninstallFailed(plugin_id, str(e)) from e
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            raise PluginUninstallFailed(plugin_id, detail)
