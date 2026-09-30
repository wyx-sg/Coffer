"""Fakes for the required-command check: the machine's commands and its
Homebrew. Nothing here runs a process — a test drives ``CliRequirementService``
against these, never against a real ``brew``."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

FAKE_BIN = "/fake/bin"
FAKE_BREW = "/fake/homebrew/bin/brew"


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


@dataclass
class FakeInstaller:
    brew: str | None = FAKE_BREW
    lines: tuple[str, ...] = ("==> Downloading", "==> Pouring", "==> Done")
    exit_code: int = 0
    #: Run while "installing" — typically puts the command on the fake PATH.
    on_run: Callable[[], None] | None = None
    #: When set, the run waits for it, so a test can look at a running job.
    gate: threading.Event | None = None
    runs: list[tuple[str, ...]] = field(default_factory=list)

    def locate(self) -> str | None:
        return self.brew

    def run(self, argv: Sequence[str], on_line: Callable[[str], None]) -> int:
        self.runs.append(tuple(argv))
        for line in self.lines:
            on_line(line)
        if self.gate is not None:
            self.gate.wait(10)
        if self.on_run is not None:
            self.on_run()
        return self.exit_code
