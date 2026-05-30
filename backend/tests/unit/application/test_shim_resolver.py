"""Unit tests for ``default_shim_resolver`` (spec 004 FR-019).

The resolver must find a ``coffer-mcp-shim`` installed as a console script in
the running interpreter's scripts directory even when the venv's ``bin`` is off
``PATH`` and ``sys.executable`` is a symlink to the base interpreter — the
common daemon-launched-from-venv case. It still honours the explicit override
and raises ``ShimNotFound`` when nothing resolves.
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
