"""``HostPlatform`` — the :class:`~coffer.application.platform_port.PlatformPort` adapter."""

from __future__ import annotations

from pathlib import Path

from coffer.application.platform_port import PlatformPort, PrivilegedPaths, TerminalLaunch
from coffer.infrastructure.platform import desktop, host, paths, terminals


class HostPlatform:
    """The running host's answers to the application's OS questions. Stateless."""

    def os_label(self) -> str:
        return host.os_label()

    def privileged_paths(self) -> PrivilegedPaths:
        return paths.privileged_paths()

    def open_command(self, target: Path, with_app: str | None) -> list[str]:
        return desktop.open_command(target, with_app)

    def reveal_command(self, target: Path) -> list[str]:
        return desktop.reveal_command(target)

    def folder_picker_command(self, start: str | None) -> list[str] | None:
        return desktop.folder_picker_command(start)

    def editor_launch_value(self, *, app_bundle: str | None, command: str | None) -> str | None:
        return desktop.editor_launch_value(app_bundle=app_bundle, command=command)

    def terminal_launch_value(self, *, app_bundle: str | None, command: str | None) -> str | None:
        return terminals.terminal_launch_value(app_bundle=app_bundle, command=command)

    def terminal_launch(self, launcher: str | None, *, command: str, cwd: str) -> TerminalLaunch:
        return terminals.terminal_launch(launcher, command=command, cwd=cwd)


def _conforms(p: HostPlatform) -> PlatformPort:
    """mypy-only conformance check, never called: mypy fails if the port stops being met."""
    return p
