"""Refusals of the required-command surfaces (spec skill-manager "Install a
required command only through Homebrew and only when asked")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CliNotRequired(CofferError):  # noqa: N818
    """No managed skill requires this command. Maps to 404."""

    code = "CLI_NOT_REQUIRED"

    def __init__(self, command: str) -> None:
        super().__init__(f"no skill requires the command {command!r}")
        self.command = command


class CliInstallNotFound(CofferError):  # noqa: N818
    """No install has run for this command since the daemon started. Maps to 404."""

    code = "CLI_INSTALL_NOT_FOUND"

    def __init__(self, command: str) -> None:
        super().__init__(f"no install has run for {command!r}")
        self.command = command


class CliFormulaMismatch(CofferError):  # noqa: N818
    """The request named a formula other than the one the skills declare. Maps to 422."""

    code = "CLI_FORMULA_MISMATCH"

    def __init__(self, command: str, declared: str, requested: str) -> None:
        super().__init__(
            f"{command!r} installs with formula {declared!r}, not {requested!r}; nothing was run"
        )
        self.error_details = {"command": command, "formula": declared}


class CliNotInstallable(CofferError):  # noqa: N818
    """Nothing to install: no formula declared, or the command is present and
    current. ``reason`` is ``no_formula`` or ``not_needed``. Maps to 409."""

    code = "CLI_NOT_INSTALLABLE"

    def __init__(self, command: str, reason: str) -> None:
        why = (
            "no skill declares a Homebrew formula for it"
            if reason == "no_formula"
            else "it is already installed and current"
        )
        super().__init__(f"{command!r} cannot be installed: {why}")
        self.reason = reason


class HomebrewNotFound(CofferError):  # noqa: N818
    """Homebrew is not on the agent's ``PATH``. Maps to 409."""

    code = "HOMEBREW_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Homebrew (brew) is not on the agent's PATH; nothing was run")


class CliInstallRunning(CofferError):  # noqa: N818
    """An install for this command is already running. Maps to 409."""

    code = "CLI_INSTALL_RUNNING"

    def __init__(self, command: str) -> None:
        super().__init__(f"an install of {command!r} is already running")
        self.command = command


__all__ = [
    "CliFormulaMismatch",
    "CliInstallNotFound",
    "CliInstallRunning",
    "CliNotInstallable",
    "CliNotRequired",
    "HomebrewNotFound",
]
