"""Errors of the daemon's settable port (spec daemon "Bind a fixed, settable port").

A port the settings page asks for is refused in place, with the reason as a
code and the facts a surface names (the range, the process holding the port)
as ``error_details`` the envelope hands over whole.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class PortOutOfRange(CofferError):  # noqa: N818
    """A port outside 1024-65535: the daemon could never bind it."""

    code = "PORT_OUT_OF_RANGE"

    def __init__(self, port: int, minimum: int, maximum: int) -> None:
        super().__init__(f"port must be a whole number from {minimum} to {maximum}, got {port}")
        self.error_details: dict[str, object] = {"port": port, "min": minimum, "max": maximum}


class PortInUse(CofferError):  # noqa: N818
    """A port another process holds; ``holder`` is ``None`` when it can't be named."""

    code = "PORT_IN_USE"

    def __init__(self, port: int, holder: dict[str, object] | None) -> None:
        if holder is None:
            message = f"port {port} is in use by another program"
        else:
            message = f"port {port} is in use by {holder['name']} (pid {holder['pid']})"
        super().__init__(message)
        self.error_details: dict[str, object] = {"port": port, "holder": holder}
