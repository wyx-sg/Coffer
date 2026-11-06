"""A fake machine for the required-command check. Nothing here runs a
process — a test drives ``CliRequirementService`` against it."""

from __future__ import annotations

from dataclasses import dataclass, field

FAKE_BIN = "/fake/bin"
#: What a test daemon reports as this machine's OS and architecture.
FAKE_MACHINE = "macOS 15.6, arm64"


@dataclass
class FakeCommand:
    """One command on the fake ``PATH``."""


@dataclass
class FakeCommandProbe:
    commands: dict[str, FakeCommand] = field(default_factory=dict)
    located: list[str] = field(default_factory=list)

    def locate(self, command: str) -> str | None:
        self.located.append(command)
        name = command.rsplit("/", 1)[-1]  # an absolute path names the same command
        return f"{FAKE_BIN}/{name}" if name in self.commands else None
