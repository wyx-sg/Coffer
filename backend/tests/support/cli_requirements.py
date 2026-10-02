"""A fake machine for the required-command check. Nothing here runs a
process — a test drives ``CliRequirementService`` against it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.application.skill.cli_discovery import HelpOutput

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
        name = command.rsplit("/", 1)[-1]  # an absolute path names the same command
        return f"{FAKE_BIN}/{name}" if name in self.commands else None

    def version(self, path: str) -> str | None:
        return self.commands[path.rsplit("/", 1)[-1]].version

    def fingerprint(self, path: str) -> str | None:
        return "fake" if path.rsplit("/", 1)[-1] in self.commands else None

    def login_ok(self, argv: Sequence[str]) -> bool | None:
        self.login_calls.append(tuple(argv))
        command = self.commands[argv[0].rsplit("/", 1)[-1]]
        _discarded = command.printed  # printed by the check, never read by Coffer
        return command.logged_in


@dataclass
class FakeHelpRunner:
    """Help texts by subcommand path; nothing runs. ``calls`` records every
    ``(path, subcommands, flag)`` the walk asked for."""

    texts: dict[tuple[str, ...], str] = field(default_factory=dict)
    calls: list[tuple[str, tuple[str, ...], str]] = field(default_factory=list)

    def run(self, path: str, subcommands: Sequence[str], flag: str) -> HelpOutput:
        self.calls.append((path, tuple(subcommands), flag))
        return HelpOutput(self.texts.get(tuple(subcommands), "") if flag == "--help" else "")


#: A tiny tool: two subcommands, one with an option of its own.
DEMO_HELP: dict[tuple[str, ...], str] = {
    (): (
        "A demo tool.\n\nUsage: demo [OPTIONS] COMMAND [ARGS]...\n\nOptions:\n"
        "  -v, --verbose  Be loud.\n  --help         Show this message and exit.\n\n"
        "Commands:\n  init  Set things up\n  run   Run it\n"
    ),
    ("init",): "Usage: demo init [OPTIONS]\n\nOptions:\n  --force  Overwrite\n",
    ("run",): "Usage: demo run [OPTIONS] TARGET\n\nArguments:\n  TARGET  What to run\n",
}
