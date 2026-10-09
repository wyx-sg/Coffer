"""Unit tests for ``default_shim_resolver`` (spec agent-registry "Install
Coffer's MCP server into an agent in one action").

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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    # Empty scripts dir + a sys.executable whose dir holds no shim.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(empty))
    monkeypatch.setattr(mcp_service.sys, "executable", str(tmp_path / "python"))

    with pytest.raises(ShimNotFound):
        default_shim_resolver()


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="a missing shim is refused with a prompt that hands finding it to an agent",
)
def test_a_missing_shim_carries_a_handoff_naming_where_coffer_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(tmp_path / "gone" / "coffer-mcp-shim"))
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(empty))
    monkeypatch.setattr(mcp_service.sys, "executable", str(tmp_path / "dist" / "python"))

    with pytest.raises(ShimNotFound) as caught:
        default_shim_resolver()

    prompt = caught.value.error_details["handoff"]["prompt"]
    assert prompt.startswith("Please find or reinstall Coffer's `coffer-mcp-shim`")
    # Where an installed Coffer keeps it, and every place Coffer looked.
    assert str(tmp_path / "home" / ".coffer" / "bin" / "coffer-mcp-shim") in prompt
    assert str(tmp_path / "gone" / "coffer-mcp-shim") in prompt
    assert str(empty) in prompt and str(tmp_path / "dist") in prompt
    assert "choose Connect again" in prompt


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


def test_the_app_daemon_names_the_deployed_shim(tmp_path, monkeypatch):
    """Coffer.app's daemon has no shim beside it in Contents/MacOS (the app keeps
    the one-folder shim in Contents/Resources); it names the one it deployed."""
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    home = tmp_path / "home"
    _versioned, public = _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    macos = tmp_path / "Coffer.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    monkeypatch.setattr(mcp_service.sys, "executable", str(macos / "coffer-daemon"))

    assert default_shim_resolver() == str(public)


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an installed daemon writes the same shim path however it was started",
)
@pytest.mark.parametrize("started_by", ["app", "terminal", "launchd"])
def test_an_installed_daemon_writes_the_deployed_shim_however_it_was_started(
    tmp_path, monkeypatch, started_by
):
    """The app's daemon (no PATH, no sibling shim), one started from a terminal
    through the public symlink, and one launchd started with some other shim
    first on its PATH all answer the same entry, so they never rewrite each
    other's agent configs."""
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    home = tmp_path / "home"
    versioned, public = _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(mcp_service.sys, "frozen", True, raising=False)
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    other = _make_shim(tmp_path / "homebrew-bin")
    if started_by == "app":
        macos = tmp_path / "Coffer.app" / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
        monkeypatch.setattr(mcp_service.sys, "executable", str(macos / "coffer-daemon"))
    elif started_by == "terminal":
        monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: str(public))
        monkeypatch.setattr(mcp_service.sys, "executable", str(versioned.parent / "coffer"))
    else:
        monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: str(other))
        monkeypatch.setattr(mcp_service.sys, "executable", str(versioned.parent / "coffer"))

    assert default_shim_resolver() == str(public)


def test_a_source_daemon_keeps_its_own_shim_beside_a_deploy(tmp_path, monkeypatch):
    """Only an installed build prefers the deploy: a source daemon runs the code
    of its own checkout and keeps the shim that came with it."""
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    home = tmp_path / "home"
    _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delattr(mcp_service.sys, "frozen", raising=False)
    venv_shim = _make_shim(tmp_path / "venv-bin")
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)
    monkeypatch.setattr(mcp_service.sysconfig, "get_path", lambda _name: str(venv_shim.parent))

    assert default_shim_resolver() == str(venv_shim.resolve())


def test_an_installed_daemon_without_a_deploy_falls_back_to_the_search(tmp_path, monkeypatch):
    monkeypatch.delenv("COFFER_MCP_SHIM_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mcp_service.sys, "frozen", True, raising=False)
    found = _make_shim(tmp_path / "bin")
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: str(found))

    assert default_shim_resolver() == str(found.resolve())


def test_the_override_still_wins_over_the_deploy_in_an_installed_build(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _deploy(home, "0.9.9")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(mcp_service.sys, "frozen", True, raising=False)
    override = _make_shim(tmp_path / "override")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(override))

    assert default_shim_resolver() == str(override.resolve())
