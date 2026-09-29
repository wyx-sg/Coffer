"""Detect installed GUI editors for the preferred-editor picker.

Spec web-ui (the preferred-editor preference) + spec daemon "Open and reveal existing
absolute paths" (the /fs surface). The preference itself is a free-form string, but
typing it blind is error-prone — so this service enumerates common code editors that are
*actually installed* on the host, letting the settings UI offer them as a picker (the
user keeps a "custom" escape hatch for anything unlisted).

Detection is per-OS because the value the open launcher
(:class:`~coffer.application.fs.open_service.FsOpenService`) expects differs —
an application-bundle name on macOS, an executable on ``PATH`` elsewhere — so
each known editor carries both, and the host decides which applies and whether
it is installed (``PlatformPort.editor_launch_value``).

The returned ``value`` is therefore exactly what ``FsOpenService`` accepts as
``with_app``. Terminal-only editors (vim, nano, …) are intentionally omitted:
the launcher detaches stdio, so a TUI editor would never surface a window.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.platform_port import PlatformPort


@dataclass(frozen=True)
class EditorOption:
    """One detected editor: a human ``label`` and the launcher ``value``."""

    label: str
    value: str


@dataclass(frozen=True)
class _Editor:
    """A known editor and how to detect/launch it on each OS."""

    label: str
    app_bundle: str | None  # .app bundle name for `open -a` (None → not on macOS)
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


class EditorDetectService:
    """Enumerate installed GUI editors for the current OS (stateless)."""

    def __init__(self, platform: PlatformPort) -> None:
        self._platform = platform

    def list_editors(self) -> list[EditorOption]:
        options: list[EditorOption] = []
        for ed in _KNOWN:
            value = self._platform.editor_launch_value(app_bundle=ed.app_bundle, command=ed.command)
            if value is not None:
                options.append(EditorOption(label=ed.label, value=value))
        return options
