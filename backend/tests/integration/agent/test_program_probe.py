"""The dependency probe against real executables on a throwaway ``PATH``
(spec agent-registry "Detect an agent by its program and its config
directory")."""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from coffer.infrastructure.agent.program_probe import ProgramProbe, UserPath


def _program(bin_dir: pathlib.Path, name: str, body: str) -> pathlib.Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _probe(program: str, *dirs: pathlib.Path, timeout: float = 5.0) -> ProgramProbe:
    path = os.pathsep.join(str(d) for d in dirs)
    return ProgramProbe(program, user_path=lambda: path, timeout=timeout)


@pytest.mark.acceptance(spec="agent-registry", scenario="read the installed program's version")
def test_the_program_on_the_path_reports_its_version(tmp_path: pathlib.Path) -> None:
    _program(tmp_path / "bin", "claude", 'echo "2.1.281 (Claude Code)"')
    info = _probe("claude", tmp_path / "bin").probe()
    assert info.found and info.path == str((tmp_path / "bin" / "claude").resolve())
    assert info.version == "2.1.281"


def test_a_program_missing_from_the_path_is_not_found(tmp_path: pathlib.Path) -> None:
    (tmp_path / "empty").mkdir()
    info = _probe("codex", tmp_path / "empty").probe()
    assert not info.found and info.version is None


def test_the_version_is_asked_once_per_binary(tmp_path: pathlib.Path) -> None:
    counter = tmp_path / "count"
    _program(tmp_path / "bin", "codex", f'echo x >> "{counter}"; echo "codex-cli 0.155.1"')
    probe = _probe("codex", tmp_path / "bin")
    assert probe.probe().version == "0.155.1"
    assert probe.probe().version == "0.155.1"
    assert counter.read_text().count("x") == 1


def test_an_upgraded_binary_is_asked_again(tmp_path: pathlib.Path) -> None:
    _program(tmp_path / "bin", "codex", 'echo "codex-cli 0.155.1"')
    probe = _probe("codex", tmp_path / "bin")
    assert probe.probe().version == "0.155.1"
    _program(tmp_path / "bin", "codex", 'echo "codex-cli 0.160.0 (upgraded)"')
    assert probe.probe().version == "0.160.0"


def test_a_hanging_program_is_installed_without_a_version(tmp_path: pathlib.Path) -> None:
    _program(tmp_path / "bin", "claude", "sleep 5")
    info = _probe("claude", tmp_path / "bin", timeout=0.3).probe()
    assert info.found and info.version is None


def test_the_first_directory_on_the_path_wins(tmp_path: pathlib.Path) -> None:
    _program(tmp_path / "a", "codex", 'echo "codex-cli 1.0.0"')
    _program(tmp_path / "b", "codex", 'echo "codex-cli 2.0.0"')
    assert _probe("codex", tmp_path / "a", tmp_path / "b").probe().version == "1.0.0"


def test_the_user_path_puts_the_login_shell_first_and_keeps_inherited_entries(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/inherited/only"]))
    calls: list[int] = []

    def shell() -> str:
        calls.append(1)
        return os.pathsep.join(["/home/me/.local/bin", "/usr/bin"])

    user_path = UserPath(shell)
    assert user_path().split(os.pathsep) == ["/home/me/.local/bin", "/usr/bin", "/inherited/only"]
    user_path()
    assert calls == [1], "the login shell is asked once per process"


def _bundle(root: pathlib.Path, name: str, version: str | None) -> pathlib.Path:
    import plistlib

    contents = root / name / "Contents"
    contents.mkdir(parents=True)
    info = {"CFBundleName": name} | ({"CFBundleShortVersionString": version} if version else {})
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    return root / name


@pytest.mark.acceptance(
    spec="agent-registry/antigravity", scenario="detect the Antigravity App without agy"
)
def test_an_app_only_install_reads_installed_with_the_app_version(tmp_path: pathlib.Path) -> None:
    from coffer.infrastructure.platform.apps import find_app_bundle

    (tmp_path / "empty").mkdir()
    app = _bundle(tmp_path / "Applications", "Antigravity.app", "2.32.2")
    probe = ProgramProbe(
        "agy",
        user_path=lambda: str(tmp_path / "empty"),
        app_bundle="Antigravity.app",
        find_app=lambda b: find_app_bundle(b, roots=(tmp_path / "Applications",)),
    )
    info = probe.probe()
    assert info.found and info.path == str(app) and info.version == "2.32.2"


def test_the_program_on_the_path_wins_over_the_app(tmp_path: pathlib.Path) -> None:
    from coffer.infrastructure.platform.apps import find_app_bundle

    _program(tmp_path / "bin", "agy", 'echo "agy 1.4.0"')
    _bundle(tmp_path / "Applications", "Antigravity.app", "2.32.2")
    probe = ProgramProbe(
        "agy",
        user_path=lambda: str(tmp_path / "bin"),
        app_bundle="Antigravity.app",
        find_app=lambda b: find_app_bundle(b, roots=(tmp_path / "Applications",)),
    )
    info = probe.probe()
    assert info.path == str((tmp_path / "bin" / "agy").resolve()) and info.version == "1.4.0"


def test_an_app_without_a_readable_version_is_still_found(tmp_path: pathlib.Path) -> None:
    from coffer.infrastructure.platform.apps import find_app_bundle

    _bundle(tmp_path / "Applications", "Antigravity.app", None)
    found = find_app_bundle("Antigravity.app", roots=(tmp_path / "Applications",))
    assert found is not None and found.version is None
    assert find_app_bundle("Missing.app", roots=(tmp_path / "Applications",)) is None
