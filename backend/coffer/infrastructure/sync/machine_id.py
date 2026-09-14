"""Find this host's stable identifier (spec vault-sync "Identity is derived").

The id must survive reinstalling and uninstalling Coffer, so it cannot be
something Coffer generates and stores. It is read from the operating system,
which keeps one for its own purposes:

* **macOS** — ``IOPlatformUUID``, held by the ``IOPlatformExpertDevice`` node.
  Tied to the hardware; survives reinstalling the OS.
* **Linux** — ``/etc/machine-id``, falling back to ``/var/lib/dbus/machine-id``
  on systems where systemd is not the one keeping it.

When neither answers — a container, an unusual distribution — a UUID is
generated once and stored at ``~/.coffer/machine-id``. That one does **not**
survive deleting ``~/.coffer``, and the caller is told so (``derived=False``)
because such a machine reappears under a new id and its old descriptor has to
be removed by hand.

The raw value never leaves this module: callers get the digest, because a
hardware identifier is not something to commit into the user's repository.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import platform
import subprocess
import uuid

from coffer.domain.sync.machine import derive_machine_id

_IOREG = ("ioreg", "-rd1", "-c", "IOPlatformExpertDevice")
_LINUX_SOURCES = ("/etc/machine-id", "/var/lib/dbus/machine-id")
_FALLBACK_FILE = "machine-id"
_TIMEOUT_S = 5.0


@dataclasses.dataclass(frozen=True, slots=True)
class MachineIdentity:
    """The published id, and whether the host vouched for it."""

    machine_id: str
    #: True when the id came from the OS, so it survives a Coffer reinstall.
    #: False when it came from the fallback file, which does not.
    derived: bool


def resolve(coffer_dir: pathlib.Path) -> MachineIdentity:
    """This host's machine identity, creating the fallback only if needed."""
    raw = _from_platform()
    if raw:
        return MachineIdentity(derive_machine_id(raw), derived=True)
    return MachineIdentity(derive_machine_id(_fallback(coffer_dir)), derived=False)


def _from_platform() -> str | None:
    system = platform.system()
    if system == "Darwin":
        return _macos_platform_uuid()
    if system == "Linux":
        return _first_readable(_LINUX_SOURCES)
    return None


def _macos_platform_uuid() -> str | None:
    """Parse ``IOPlatformUUID`` out of ioreg's plain-text dump.

    ioreg is on every macOS; a missing binary or a changed output shape falls
    through to the file fallback rather than failing the daemon's start.
    """
    try:
        done = subprocess.run(
            _IOREG, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    for line in done.stdout.splitlines():
        if "IOPlatformUUID" not in line:
            continue
        # `      "IOPlatformUUID" = "1E4C…"`
        parts = line.split('"')
        if len(parts) >= 4 and parts[-2].strip():
            return parts[-2].strip()
    return None


def _first_readable(paths: tuple[str, ...]) -> str | None:
    for path in paths:
        try:
            value = pathlib.Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return None


def _fallback(coffer_dir: pathlib.Path) -> str:
    """Read, or create once, the locally-stored identifier.

    Written ``0600`` and never rewritten: regenerating it would split this
    machine's identity in two, which is the failure the whole module exists to
    avoid.
    """
    path = coffer_dir / _FALLBACK_FILE
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    value = uuid.uuid4().hex
    coffer_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)
    return value
