"""This machine's identity, resolved once and cached (spec vault-sync).

Two things, and they are not the same kind of thing at all:

* ``machine_id`` is **derived from the host** by
  :mod:`coffer.infrastructure.sync.machine_id`. It keys this machine's
  descriptor and its registry row (a channel's binding and the curation owner
  name it too) — and it
  must survive reinstalling Coffer, because an id that changed would make a
  returning machine look like a brand-new one to the remote.
  ``daemon-config.json`` only **caches** it — a
  lost cache recomputes to the same value, because the host is what produces
  it. Deriving it means reading ``ioreg`` on macOS, which is cheap but not free,
  and the daemon asks for it on every boot.
* ``machine_name`` is a label the user may change at any time, at no cost,
  because nothing references it. It lives in the same file for a different
  reason: the daemon needs a name before it has published anything.

``derived`` is never cached, because it is a fact about *where the id came
from* and only the host can answer it. It is recovered without shelling out:
the id is a fallback id exactly when the fallback file exists and hashes to it.
That matters to the user — a machine on the fallback does not survive deleting
``~/.coffer``, and its stale descriptor has to be retired by hand.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.sync.machine import derive_machine_id
from coffer.infrastructure.daemon.config import (
    read_cached_machine_id,
    read_machine_name,
    write_cached_machine_id,
)
from coffer.infrastructure.sync.machine_id import MachineIdentity, resolve

_FALLBACK_FILE = "machine-id"


def coffer_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer"


def resolve_identity(root: pathlib.Path | None = None) -> MachineIdentity:
    """This machine's id, from the cache when there is one.

    The cache is a shortcut, not a source of truth: it is only ever written
    with a value the host produced, and deleting it costs one ``ioreg`` call
    rather than this machine's identity.
    """
    directory = root if root is not None else coffer_dir()
    cached = read_cached_machine_id()
    if cached:
        return MachineIdentity(cached, derived=not _is_fallback(directory, cached))
    identity = resolve(directory)
    write_cached_machine_id(identity.machine_id)
    return identity


def machine_name() -> str:
    """The display name for this machine (hostname unless the user set one)."""
    return read_machine_name()


def _is_fallback(directory: pathlib.Path, machine_id: str) -> bool:
    """Whether ``machine_id`` came from the locally-stored fallback identifier."""
    try:
        raw = (directory / _FALLBACK_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not raw:
        return False
    return derive_machine_id(raw) == machine_id
