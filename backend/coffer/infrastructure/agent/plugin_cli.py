"""CLI-mediated plugin uninstall for Claude Code.

Claude Code records a plugin's installed state in an internal file
(``~/.claude/plugins/installed_plugins.json``) that Coffer treats as read-only —
hand-editing it risks corrupting Claude's plugin state. Instead, uninstall is
delegated to Claude's own ``claude plugin uninstall <id>`` command, which owns
that state (and removes the cache dir). This adapter implements the
application-layer ``PluginCliRunner`` Protocol so the service never spawns
subprocesses itself.

``available()`` gates the in-app uninstall affordance on the CLI being present;
when it is not, the UI says so and offers the agent's reinstall hand-off. The
CLI is looked up on the agent's real ``PATH`` (``UserPath``) — the one agent
detection finds ``claude`` on — so an installed Claude Code never reads as
missing here only because the daemon was started with a shorter ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping

from coffer.domain.workspace_errors import PluginUninstallFailed

# Bound the subprocess so a hung CLI can't wedge the request handler.
_UNINSTALL_TIMEOUT_S = 120


class ClaudePluginCli:
    """Runs ``claude plugin uninstall`` for CLI-strategy (Claude) uninstall."""

    def __init__(
        self, executable: str = "claude", *, user_path: Callable[[], str] | None = None
    ) -> None:
        self._executable = executable
        self._user_path = user_path

    def _resolve(self) -> str | None:
        if self._user_path is None:
            return shutil.which(self._executable)
        return shutil.which(self._executable, path=self._user_path())

    def available(self) -> bool:
        return self._resolve() is not None

    def uninstall(self, plugin_id: str, *, env: Mapping[str, str] | None = None) -> None:
        """Run ``claude plugin uninstall <plugin_id>``.

        ``env`` overrides the inherited environment — ``CLAUDE_CONFIG_DIR`` for
        an agent whose config dir is not the default, so the CLI uninstalls
        from that agent's directory rather than from ``~/.claude``.

        Raises :class:`PluginUninstallFailed` if the CLI is missing, exits
        non-zero, or times out — the service maps that to an actionable error
        rather than leaving the user with a silent no-op.
        """
        program = self._resolve()
        if program is None:
            raise PluginUninstallFailed(plugin_id, "the `claude` CLI is not on PATH")
        try:
            proc = subprocess.run(
                [program, "plugin", "uninstall", plugin_id],
                capture_output=True,
                text=True,
                timeout=_UNINSTALL_TIMEOUT_S,
                check=False,
                env={**os.environ, **env} if env else None,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise PluginUninstallFailed(plugin_id, str(e)) from e
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            raise PluginUninstallFailed(plugin_id, detail)
