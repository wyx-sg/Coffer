"""A fixed-answer ``PlatformPort`` for the fs use cases: no OS is consulted."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from coffer.application.platform_port import PrivilegedPaths, TerminalLaunch


@dataclasses.dataclass
class FakePlatform:
    picker: list[str] | None = dataclasses.field(default_factory=lambda: ["picker"])
    editors: dict[str, str] = dataclasses.field(default_factory=dict)
    picker_starts: list[str | None] = dataclasses.field(default_factory=list)
    terminals: dict[str, str] = dataclasses.field(default_factory=dict)
    terminal_launches: list[tuple[str | None, str, str]] = dataclasses.field(default_factory=list)

    def os_label(self) -> str:
        return "TestOS 1.0"

    def privileged_paths(self) -> PrivilegedPaths:
        return PrivilegedPaths(prefixes=(), carve_outs=(), separator="/", firmlink_root=None)

    def open_command(self, target: Path, with_app: str | None) -> list[str]:
        return ["open-with", with_app or "<default>", str(target)]

    def reveal_command(self, target: Path) -> list[str]:
        return ["reveal", str(target)]

    def folder_picker_command(self, start: str | None) -> list[str] | None:
        self.picker_starts.append(start)
        return self.picker

    def editor_launch_value(self, *, app_bundle: str | None, command: str | None) -> str | None:
        return self.editors.get(app_bundle or command or "")

    def terminal_launch_value(self, *, app_bundle: str | None, command: str | None) -> str | None:
        return self.terminals.get(app_bundle or command or "")

    def terminal_launch(self, launcher: str | None, *, command: str, cwd: str) -> TerminalLaunch:
        self.terminal_launches.append((launcher, command, cwd))
        return TerminalLaunch(["fake-terminal", launcher or "<system>", command])
