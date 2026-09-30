"""A fake machine for the required-command check. Nothing here runs a
process — a test drives ``CliRequirementService`` against it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

FAKE_BIN = "/fake/bin"
#: What a test daemon reports as this machine's OS and architecture.
FAKE_MACHINE = "macOS 15.6, arm64"


@dataclass
class FakeCommand:
    """One command on the fake ``PATH``. ``printed`` is what its login check
    would print — a real check may print an account name, which must never
    reach a response, a log line or an audit record."""

    version: str | None = None
    logged_in: bool | None = True
    printed: str = ""


@dataclass
class FakeCommandProbe:
    commands: dict[str, FakeCommand] = field(default_factory=dict)
    located: list[str] = field(default_factory=list)
    login_calls: list[tuple[str, ...]] = field(default_factory=list)

    def locate(self, command: str) -> str | None:
        self.located.append(command)
        return f"{FAKE_BIN}/{command}" if command in self.commands else None

    def version(self, path: str) -> str | None:
        return self.commands[path.rsplit("/", 1)[-1]].version

    def login_ok(self, argv: Sequence[str]) -> bool | None:
        self.login_calls.append(tuple(argv))
        command = self.commands[argv[0].rsplit("/", 1)[-1]]
        _discarded = command.printed  # printed by the check, never read by Coffer
        return command.logged_in
