"""The ``apiKeyHelper`` names the ``coffer`` CLI by absolute path.

Claude Code launched from the Dock does not get the login shell's ``PATH``, so
a bare ``coffer`` in its ``settings.json`` is a helper that cannot run. The
resolver finds the CLI the way the MCP entry finds the shim, and the projector
writes what it found.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import UTC, datetime

import pytest

from coffer.application.provider import cli_path
from coffer.application.provider.projector import ProviderProjector
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore

_NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _executable(path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def _nothing_else(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No scripts dir and no sibling binary, so only the branch under test answers."""
    monkeypatch.setattr(cli_path.sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "none" / "python"))


def test_a_cli_on_path_is_named_by_its_absolute_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = _executable(tmp_path / "venv" / "bin" / "coffer")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(cli.parent))
    _nothing_else(monkeypatch, tmp_path)

    assert cli_path.default_coffer_cli_resolver() == str(cli.resolve())


def test_a_deployed_cli_is_named_by_its_public_link_not_its_version_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    bin_dir = home / ".coffer" / "bin"
    versioned = _executable(bin_dir / "0.4.0" / "coffer")
    (bin_dir / "coffer").symlink_to(versioned)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(versioned.parent))  # finds the version dir itself
    _nothing_else(monkeypatch, tmp_path)

    assert cli_path.default_coffer_cli_resolver() == str(bin_dir / "coffer")


def test_a_cli_beside_the_running_binary_is_found_off_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = tmp_path / "dist"
    _executable(frozen / "coffer-daemon")
    cli = _executable(frozen / "coffer")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(cli_path.sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    monkeypatch.setattr(sys, "executable", str(frozen / "coffer-daemon"))

    assert cli_path.default_coffer_cli_resolver() == str(cli.resolve())


def test_no_cli_anywhere_falls_back_to_the_bare_name(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    _nothing_else(monkeypatch, tmp_path)

    assert cli_path.default_coffer_cli_resolver() == "coffer"


def test_the_projector_writes_the_resolved_cli_into_settings(tmp_path: pathlib.Path) -> None:
    agent_uid = "8f1c2d3e4a5b6c7d8e9f0a1b2c3d4e5f"
    connection_uid = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"
    agent = Resource(
        id=1,
        uid=agent_uid,
        kind="agent",
        name="claude-code",
        description=None,
        config={"type": "claude_code", "config_dir": str(tmp_path)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    config = {
        "protocol": "anthropic",
        "base_url": "https://gw.example/anthropic",
        "credential_ref": "gw-key",
    }
    connection = Resource(
        id=2,
        uid=connection_uid,
        kind="provider",
        name="gw",
        description=None,
        config=config,
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    projector = ProviderProjector(
        ConfigFileStore(), cli_resolver=lambda: "/Users/me/My Apps/coffer"
    )

    projector.project_type(
        connection, ProviderConfig.model_validate(config), [agent], AgentType.CLAUDE_CODE
    )

    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["apiKeyHelper"] == (
        f"'/Users/me/My Apps/coffer' provider key --connection-uid {connection_uid}"
    )
