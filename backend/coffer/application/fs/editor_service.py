"""Detect installed GUI editors for the preferred-editor picker.

Spec 002-ui-shell (the preferred-editor preference) + spec 004-agent-registry
FR-039 (the /fs surface). The preference itself is a free-form string, but
typing it blind is error-prone — so this service enumerates common code editors
that are *actually installed* on the host, letting the settings UI offer them as
a picker (the user keeps a "custom" escape hatch for anything unlisted).

Detection is per-OS because the value the open launcher
(:class:`~coffer.application.fs.open_service.FsOpenService`) expects differs:

* **macOS** — ``open -a <app>`` wants an application *name*; we look for the app
  bundle under ``/Applications`` and ``~/Applications`` and return the app name.
* **Linux / Windows** — the launcher runs the value as an executable; we look it
  up on ``PATH`` with :func:`shutil.which` and return the command.

The returned ``value`` is therefore exactly what ``FsOpenService`` accepts as
``with_app``. Terminal-only editors (vim, nano, …) are intentionally omitted:
the launcher detaches stdio, so a TUI editor would never surface a window.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EditorOption:
    """One detected editor: a human ``label`` and the launcher ``value``."""

    label: str
    value: str


@dataclass(frozen=True)
class _Editor:
    """A known editor and how to detect/launch it on each OS."""

    label: str
    mac_app: str | None  # .app bundle name for `open -a` (None → not on macOS)
    command: str | None  # executable on PATH for Linux/Windows (None → GUI-only)


# Curated, ordered list of common GUI code editors. Order is the display order.
_KNOWN: tuple[_Editor, ...] = (
    _Editor("Visual Studio Code", "Visual Studio Code", "code"),
    _Editor("Cursor", "Cursor", "cursor"),
    _Editor("Windsurf", "Windsurf", "windsurf"),
    _Editor("Zed", "Zed", "zed"),
    _Editor("Sublime Text", "Sublime Text", "subl"),
    _Editor("VSCodium", "VSCodium", "codium"),
    _Editor("IntelliJ IDEA", "IntelliJ IDEA", "idea"),
    _Editor("PyCharm", "PyCharm", "pycharm"),
    _Editor("WebStorm", "WebStorm", "webstorm"),
    _Editor("Nova", "Nova", None),
    _Editor("BBEdit", "BBEdit", "bbedit"),
    _Editor("Xcode", "Xcode", None),
    _Editor("Emacs", "Emacs", None),  # GUI Emacs.app on macOS
    _Editor("Gedit", None, "gedit"),
    _Editor("Kate", None, "kate"),
)


def _mac_app_dirs() -> tuple[Path, ...]:
    return (Path("/Applications"), Path.home() / "Applications")


def _mac_app_installed(app_name: str) -> bool:
    """True if ``<app_name>.app`` exists in a standard macOS applications dir."""
    return any((root / f"{app_name}.app").is_dir() for root in _mac_app_dirs())


class EditorDetectService:
    """Enumerate installed GUI editors for the current OS (stateless)."""

    def list_editors(self) -> list[EditorOption]:
        if sys.platform == "darwin":
            return [
                EditorOption(label=ed.label, value=ed.mac_app)
                for ed in _KNOWN
                if ed.mac_app is not None and _mac_app_installed(ed.mac_app)
            ]
        # Linux / Windows / other: anything resolvable on PATH.
        return [
            EditorOption(label=ed.label, value=ed.command)
            for ed in _KNOWN
            if ed.command is not None and shutil.which(ed.command) is not None
        ]
