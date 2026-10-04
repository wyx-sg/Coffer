"""Errors of opening an agent session in a terminal (spec daemon "Open an agent
session in a terminal")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class FsTerminalInvalid(CofferError):  # noqa: N818
    """The request cannot become a command: an unknown agent, an unsafe session
    id, a relative directory, both or neither of ``resume`` and ``prompt``, or a
    terminal template without ``{command}``. Raised before anything is started."""

    code = "FS_TERMINAL_INVALID"

    def __init__(self, reason: str) -> None:
        super().__init__(f"cannot open a terminal: {reason}")
        self.reason = reason


class FsTerminalFailed(CofferError):  # noqa: N818
    """The terminal launcher could not be started (not installed, spawn failed,
    no terminal found on this host)."""

    code = "FS_TERMINAL_FAILED"

    def __init__(self, reason: str) -> None:
        super().__init__(f"the terminal could not be started: {reason}")
        self.reason = reason
