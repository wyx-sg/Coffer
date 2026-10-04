"""A plaintext secret a round found in what it was about to push
(spec vault-sync "Refuse to push a plaintext secret").

The remote is a repository the person owns, but a value pushed there is out of
Coffer's hands for good: it is in the remote's history, in every clone, and in
any backup of either. So before a round pushes, every file the push would
publish — each blob the remote does not already hold, from every commit since
the remote's head — is read for a plaintext secret, with the same detection
the Secrets page's scan uses. An encrypted ``secret/<ref>.enc`` file is
ciphertext and is not read.

A finding names the file, the line and the name the value was assigned to,
and the blob it was found in. It never carries the value.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.plaintext_shape import MaskedValue


@dataclass(frozen=True)
class PlaintextFinding:
    path: str
    #: 1-based.
    line: int
    #: The name the value is assigned to (``DB_PASSWORD``), or ``token`` for
    #: a value recognised by its shape alone.
    key: str
    #: The blob the value is in. "Push anyway" allows exactly these blobs, so
    #: a file changed since is read again.
    blob: str
    #: Whether the file still holds it at the commit being pushed. A value
    #: that is only in an earlier, unpushed commit is not in any file any more.
    current: bool = True


@dataclass(frozen=True)
class MaskedLine:
    """One line of a file as the person may see it: every plaintext value on
    it masked (spec vault-sync "Show a plaintext finding in its file")."""

    number: int
    text: str
    values: tuple[MaskedValue, ...] = ()


@dataclass(frozen=True)
class PlaintextContext:
    """A finding in its file, computed when asked and never stored.

    ``change`` is ``added`` when the remote does not hold the file and
    ``modified`` when it does; ``on_remote`` says the flagged line is already
    in the remote's copy. ``diff`` is the file's change against the remote's
    copy, masked line by line, for a ``modified`` file small enough to show."""

    finding: PlaintextFinding
    change: str
    on_remote: bool
    lines: tuple[MaskedLine, ...]
    diff: str | None = None
    added: int = 0
    removed: int = 0


__all__ = ["MaskedLine", "PlaintextContext", "PlaintextFinding"]
