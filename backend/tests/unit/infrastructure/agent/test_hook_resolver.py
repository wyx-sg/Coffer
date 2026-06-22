"""Unit tests for ``default_hook_resolver`` (Slice 6).

Mirrors ``default_shim_resolver``: env override → PATH → sysconfig scripts dir →
bundled binary next to the executable; raises ``ShimNotFound`` when nothing
resolves.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.errors import ShimNotFound
from coffer.infrastructure.agent import hook_resolver
from coffer.infrastructure.agent.hook_resolver import default_hook_resolver


def _make_hook(directory: pathlib.Path) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / "coffer-hook"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def test_resolves_via_interpreter_scripts_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("COFFER_HOOK_PATH", raising=False)
    monkeypatch.setattr(hook_resolver.shutil, "which", lambda _name: None)
    scripts = tmp_path / "venv-bin"
    binary = _make_hook(scripts)
    monkeypatch.setattr(hook_resolver.sysconfig, "get_path", lambda _name: str(scripts))

    assert default_hook_resolver() == str(binary.resolve())


def test_override_takes_precedence(tmp_path, monkeypatch):
    override = _make_hook(tmp_path / "override")
    monkeypatch.setenv("COFFER_HOOK_PATH", str(override))
    monkeypatch.setattr(hook_resolver.shutil, "which", lambda _name: "/usr/bin/coffer-hook")

    assert default_hook_resolver() == str(override.resolve())


def test_resolves_via_path(tmp_path, monkeypatch):
    monkeypatch.delenv("COFFER_HOOK_PATH", raising=False)
    binary = _make_hook(tmp_path / "onpath")
    monkeypatch.setattr(hook_resolver.shutil, "which", lambda _name: str(binary))

    assert default_hook_resolver() == str(binary.resolve())


def test_raises_when_nothing_resolves(tmp_path, monkeypatch):
    monkeypatch.delenv("COFFER_HOOK_PATH", raising=False)
    monkeypatch.setattr(hook_resolver.shutil, "which", lambda _name: None)
    monkeypatch.setattr(hook_resolver.sysconfig, "get_path", lambda _name: str(tmp_path / "none"))
    monkeypatch.setattr(hook_resolver.sys, "executable", str(tmp_path / "py" / "python"))

    with pytest.raises(ShimNotFound):
        default_hook_resolver()
