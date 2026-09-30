"""Find this host's stable identifier (spec vault-sync "Derive machine identity from the host").

The id must survive reinstalling and uninstalling Coffer, so it cannot be
something Coffer generates and stores. It is read from the operating system,
which keeps one for its own purposes — ``IOPlatformUUID`` on macOS,
``/etc/machine-id`` on Linux (see ``coffer.infrastructure.platform.identity``
for where each OS keeps it).

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
import uuid

from coffer.domain.sync.machine import derive_machine_id
from coffer.infrastructure.platform.identity import os_machine_id
from coffer.infrastructure.vault.home import MACHINE_ID_FILENAME


@dataclasses.dataclass(frozen=True, slots=True)
class MachineIdentity:
    """The published id, and whether the host vouched for it."""

    machine_id: str
    #: True when the id came from the OS, so it survives a Coffer reinstall.
    #: False when it came from the fallback file, which does not.
    derived: bool


def resolve(coffer_dir: pathlib.Path) -> MachineIdentity:
    """This host's machine identity, creating the fallback only if needed."""
    raw = os_machine_id()
    if raw:
        return MachineIdentity(derive_machine_id(raw), derived=True)
    return MachineIdentity(derive_machine_id(_fallback(coffer_dir)), derived=False)


def _fallback(coffer_dir: pathlib.Path) -> str:
    """Read, or create once, the locally-stored identifier.

    Written ``0600`` and never rewritten: regenerating it would split this
    machine's identity in two, which is the failure the whole module exists to
    avoid.
    """
    path = coffer_dir / MACHINE_ID_FILENAME
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
