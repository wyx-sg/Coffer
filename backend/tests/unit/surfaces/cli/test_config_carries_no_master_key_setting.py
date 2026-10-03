"""`coffer config` has no master-key setting and imports no secret code (spec secret)."""

from __future__ import annotations

import ast
import pathlib

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app

_CLI = pathlib.Path(__file__).resolve().parents[4] / "coffer" / "surfaces" / "cli"
_CONFIG_MODULES = ("config_cmd.py", "_config_keys.py", "_config_registry.py")


@pytest.mark.acceptance(spec="secret", scenario="the config command carries no master key setting")
def test_the_config_command_has_no_master_key_setting_and_imports_no_secret_code() -> None:
    for name in _CONFIG_MODULES:
        tree = ast.parse((_CLI / name).read_text())
        imported = {
            n.module if isinstance(n, ast.ImportFrom) else alias.name
            for n in ast.walk(tree)
            if isinstance(n, ast.Import | ast.ImportFrom)
            for alias in n.names
        }
        assert not any(m and (m == "keyring" or m.startswith("keyring.")) for m in imported), name
        assert not any(m and m.startswith("coffer.infrastructure.secret") for m in imported), name

    runner = CliRunner()
    for argv in (("get", "secrets.storage"), ("set", "secrets.storage", "keychain")):
        r = runner.invoke(cli_app, ["config", *argv])
        assert r.exit_code != 0, r.output
        assert "unknown setting" in r.output
