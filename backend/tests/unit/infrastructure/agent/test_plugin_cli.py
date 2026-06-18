"""Unit tests for ClaudePluginCli — PATH gating, argv, and failure mapping.

All subprocess calls are mocked; nothing is actually run.
"""

from __future__ import annotations

from unittest import mock

import pytest

from coffer.domain.workspace_errors import PluginUninstallFailed
from coffer.infrastructure.agent.plugin_cli import ClaudePluginCli


def test_available_reflects_path() -> None:
    with mock.patch("shutil.which", return_value="/usr/bin/claude"):
        assert ClaudePluginCli().available() is True
    with mock.patch("shutil.which", return_value=None):
        assert ClaudePluginCli().available() is False


def test_uninstall_runs_expected_argv() -> None:
    with (
        mock.patch("shutil.which", return_value="/usr/bin/claude"),
        mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ) as run,
    ):
        ClaudePluginCli().uninstall("plugin-a@npm")
    run.assert_called_once()
    assert run.call_args.args[0] == ["claude", "plugin", "uninstall", "plugin-a@npm"]


def test_uninstall_missing_cli_raises() -> None:
    with mock.patch("shutil.which", return_value=None), pytest.raises(PluginUninstallFailed):
        ClaudePluginCli().uninstall("x@y")


def test_uninstall_nonzero_exit_raises_with_message() -> None:
    with (
        mock.patch("shutil.which", return_value="/usr/bin/claude"),
        mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=1, stdout="", stderr="no such plugin"),
        ),
        pytest.raises(PluginUninstallFailed) as ei,
    ):
        ClaudePluginCli().uninstall("x@y")
    assert "no such plugin" in str(ei.value)


def test_uninstall_subprocess_error_raises() -> None:
    # A spawn failure / timeout (OSError or SubprocessError) maps to a clean
    # PluginUninstallFailed rather than bubbling the raw exception.
    with (
        mock.patch("shutil.which", return_value="/usr/bin/claude"),
        mock.patch("subprocess.run", side_effect=OSError("spawn failed")),
        pytest.raises(PluginUninstallFailed),
    ):
        ClaudePluginCli().uninstall("x@y")
