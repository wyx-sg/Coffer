"""Unit tests for ``default_shim_resolver`` (spec agent-registry FR-015).

The resolver must find a ``coffer-mcp-shim`` installed as a console script in
the running interpreter's scripts directory even when the venv's ``bin`` is off
``PATH`` and ``sys.executable`` is a symlink to the base interpreter — the
common daemon-launched-from-venv case. It still honours the explicit override
and raises ``ShimNotFound`` when nothing resolves.

It also has to name a deployed shim by the public
``~/.coffer/bin/coffer-mcp-shim``, never by the version directory that symlink
points into: the path it returns is written into an agent's config file, and a
later deploy prunes older version directories.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent import mcp_service
from coffer.application.agent.mcp_service import default_shim_resolver
from coffer.domain.errors import ShimNotFound


def _make_shim(directory: pathlib.Path) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    shim.chmod(0o755)
    return shim


def test_resolves_via_interpreter_scripts_dir(tmp_path, monkeypatch):
    """A shim in sysconfig's scripts dir resolves even when off PATH."""
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    scripts = tmp_path / "venv-bin"
    shim = _make_shim(scripts)
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(scripts))

    assert default_shim_resolver() == str(shim.resolve())


def test_override_takes_precedence(tmp_path, monkeypatch):
    override = _make_shim(tmp_path / "override")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(override))
    # which / sysconfig would resolve elsewhere, but the override wins.
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: "/usr/bin/coffer-mcp-shim")

    assert default_shim_resolver() == str(override.resolve())


def test_raises_when_nothing_resolves(tmp_path, monkeypatch):
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    # Empty scripts dir + a sys.executable whose dir holds no shim.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(empty))
    monkeypatch.setattr(mcp_service.sys, "executable", str(tmp_path / "python"))

    with pytest.raises(ShimNotFound):
        default_shim_resolver()


def _deploy(home: pathlib.Path, version: str) -> tuple[pathlib.Path, pathlib.Path]:
    """A frozen deploy under `home`: the version directory's shim and the
    public symlink into it, the way `binary_deploy` lays them out."""
    versioned = _make_shim(home / ".coffer" / "bin" / version)
    public = versioned.parent.parent / "coffer-mcp-shim"
    public.symlink_to(versioned)
    return versioned, public


def test_deployed_shim_is_named_by_its_public_symlink(tmp_path, monkeypatch):
    """`which` finding the public name must not collapse it to the version dir."""
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    home = tmp_path / "home"
    _versioned, public = _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: str(public))

    assert default_shim_resolver() == str(public)


def test_cli_started_through_the_symlink_still_reports_the_public_name(tmp_path, monkeypatch):
    """The bundled branch sees the version directory; it answers the public name.

    A CLI launched as `~/.coffer/bin/coffer` resolves to
    `~/.coffer/bin/<version>/coffer`, so its sibling shim is the versioned copy.
    """
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    home = tmp_path / "home"
    versioned, public = _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    monkeypatch.setattr(mcp_service.sys, "executable", str(versioned.parent / "coffer"))

    assert default_shim_resolver() == str(public)


def test_a_shim_outside_the_deploy_is_left_alone(tmp_path, monkeypatch):
    """A venv console script keeps resolving to itself, deploy present or not."""
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    home = tmp_path / "home"
    _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    venv_shim = _make_shim(tmp_path / "venv-bin")
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: str(venv_shim))

    assert default_shim_resolver() == str(venv_shim.resolve())
