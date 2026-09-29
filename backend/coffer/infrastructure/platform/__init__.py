"""The one package that knows which operating system Coffer runs on.

Everything OS-specific lives here: identifying the host (``host``), the
privileged-path rules (``paths``), desktop file actions (``desktop``),
directory links — symlink / junction / copy (``links``), process spawning and
the login-service manager (``process``), and the OS-kept machine id
(``identity``). The application reaches it only through
:class:`~coffer.application.platform_port.PlatformPort`, whose adapter is
:class:`HostPlatform`; other infrastructure imports these modules directly.

``scripts/check_platform_calls.py`` fails the build on an OS check outside this
package. Only macOS is released; the Windows and Linux branches keep the
foundation portable and are exercised by unit tests, not by a release.
"""

from __future__ import annotations

from coffer.infrastructure.platform.adapter import HostPlatform
from coffer.infrastructure.platform.host import HostOs, host_os

__all__ = ["HostOs", "HostPlatform", "host_os"]
