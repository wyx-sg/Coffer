"""The machine-level files an uninstall removes (spec daemon "Uninstall Coffer
from this machine").

Each function removes what it finds and returns what that was — an empty list
means there was nothing to remove — and raises when a removal fails:

- the start-at-login job (``~/Library/LaunchAgents/dev.coffer.daemon.plist``);
- the Warp launch configurations a terminal launch wrote
  (``~/.warp/launch_configurations/coffer-*.yaml``);
- the installer's ``PATH`` lines: ``install.sh`` appends a blank line, the
  marker ``# Added by Coffer installer`` and one ``export PATH=…`` (or fish's
  ``fish_add_path …``) line to the profile of the person's shell;
- ``~/.coffer/bin``, the frozen binaries and their versioned folders.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from coffer.infrastructure.daemon import login_service
from coffer.infrastructure.vault.home import bin_dir, coffer_home

#: The line ``install.sh`` writes above the one it adds.
PATH_MARKER = "# Added by Coffer installer"


def remove_login_job() -> list[str]:
    if not login_service.is_supported() or not login_service.is_installed():
        return []
    path = login_service.plist_path()
    login_service.uninstall()
    return [str(path)]


def remove_terminal_files(home: Path | None = None) -> list[str]:
    folder = (home or Path.home()) / ".warp" / "launch_configurations"
    removed: list[str] = []
    for path in sorted(folder.glob("coffer-*.yaml")):
        path.unlink(missing_ok=True)
        removed.append(str(path))
    return removed


def profile_candidates(home: Path | None = None) -> list[Path]:
    """Every profile ``install.sh`` may have written to, whatever the shell is now."""
    base = home or Path.home()
    zdot = Path(os.environ["ZDOTDIR"]) if os.environ.get("ZDOTDIR") and home is None else base
    xdg = (
        Path(os.environ["XDG_CONFIG_HOME"])
        if os.environ.get("XDG_CONFIG_HOME") and home is None
        else base / ".config"
    )
    paths = [
        zdot / ".zshrc",
        base / ".bash_profile",
        base / ".bashrc",
        xdg / "fish" / "config.fish",
        base / ".profile",
    ]
    return list(dict.fromkeys(paths))


def strip_path_lines(text: str) -> str:
    """``text`` without each installer block: the marker, the line after it, and
    the blank line the installer put before the marker."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip("\r\n") == PATH_MARKER:
            if out and not out[-1].strip():
                out.pop()
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def remove_path_lines(home: Path | None = None) -> list[str]:
    changed: list[str] = []
    for profile in profile_candidates(home):
        try:
            text = profile.read_text("utf-8")
        except FileNotFoundError:
            continue
        if PATH_MARKER not in text:
            continue
        stripped = strip_path_lines(text)
        if stripped == text:
            continue
        tmp = profile.with_name(f".{profile.name}.coffer-uninstall")
        tmp.write_text(stripped, "utf-8")
        # Keep the profile's own mode (a 0600 .zshrc stays 0600).
        shutil.copymode(profile, tmp)
        os.replace(tmp, profile)
        changed.append(str(profile))
    return changed


def remove_binaries(home: Path | None = None) -> list[str]:
    folder = bin_dir(home)
    if not folder.exists() and not folder.is_symlink():
        return []
    # Only the folder under Coffer's own home, never a path it points at.
    if folder.parent.resolve() != coffer_home(home).resolve():
        raise RuntimeError(f"{folder} is not inside {coffer_home(home)}; left in place")
    if folder.is_symlink():
        folder.unlink()
    else:
        shutil.rmtree(folder)
    return [str(folder)]


__all__ = [
    "PATH_MARKER",
    "profile_candidates",
    "remove_binaries",
    "remove_login_job",
    "remove_path_lines",
    "remove_terminal_files",
    "strip_path_lines",
]
