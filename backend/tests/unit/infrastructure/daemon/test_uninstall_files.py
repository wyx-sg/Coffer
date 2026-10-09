"""The machine-level files an uninstall removes (spec daemon "Uninstall Coffer
from this machine")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.daemon import uninstall_files
from coffer.infrastructure.daemon.uninstall_files import (
    PATH_MARKER,
    remove_binaries,
    remove_path_lines,
    remove_terminal_files,
    strip_path_lines,
)

_BLOCK = f'\n{PATH_MARKER}\nexport PATH="/h/.coffer/bin:$PATH"\n'


def test_the_installer_block_goes_with_its_blank_line_and_nothing_else() -> None:
    text = "alias ll='ls -l'\n" + _BLOCK + "export EDITOR=vim\n"
    assert strip_path_lines(text) == "alias ll='ls -l'\nexport EDITOR=vim\n"
    assert strip_path_lines("nothing of ours\n") == "nothing of ours\n"


def test_every_profile_the_installer_wrote_is_cleaned(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ZDOTDIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("export A=1\n" + _BLOCK)
    zshrc.chmod(0o600)
    fish = tmp_path / ".config" / "fish" / "config.fish"
    fish.parent.mkdir(parents=True)
    fish.write_text(f"\n{PATH_MARKER}\nfish_add_path /h/.coffer/bin\n")
    (tmp_path / ".bashrc").write_text("untouched\n")
    changed = remove_path_lines(tmp_path)
    assert sorted(changed) == sorted([str(zshrc), str(fish)])
    assert zshrc.read_text() == "export A=1\n"
    assert zshrc.stat().st_mode & 0o777 == 0o600
    assert fish.read_text() == ""
    assert remove_path_lines(tmp_path) == []


def test_only_coffers_warp_launch_files_go(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / ".warp" / "launch_configurations"
    folder.mkdir(parents=True)
    (folder / "coffer-abc.yaml").write_text("x")
    (folder / "mine.yaml").write_text("y")
    assert remove_terminal_files(tmp_path) == [str(folder / "coffer-abc.yaml")]
    assert (folder / "mine.yaml").exists()
    assert remove_terminal_files(tmp_path) == []


def test_the_binaries_folder_goes_and_a_missing_one_is_nothing(tmp_path: pathlib.Path) -> None:
    bin_dir = tmp_path / ".coffer" / "bin"
    (bin_dir / "0.3.0").mkdir(parents=True)
    (bin_dir / "coffer").symlink_to("0.3.0/coffer")
    assert remove_binaries(tmp_path) == [str(bin_dir)]
    assert not bin_dir.exists() and (tmp_path / ".coffer").exists()
    assert remove_binaries(tmp_path) == []


def test_no_login_job_is_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uninstall_files.login_service, "is_supported", lambda: True)
    monkeypatch.setattr(uninstall_files.login_service, "is_installed", lambda: False)
    assert uninstall_files.remove_login_job() == []
