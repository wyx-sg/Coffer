"""Where a credential ref's ciphertext file lives (ADR storage-is-five-classes-by-nature).

A ref is an opaque name (``channel/seatalk/app-secret``, ``secret/github``),
and its ciphertext is one file per ref whose path *is* that name: ``/``
separates directories, and ``.enc`` is appended to the last segment. So the
tree under ``credentials/`` reads as the list of refs, and the file names are
the ones sync already carried as ``credentials/<ref>.enc``.

A ref is a name, never a path a caller may aim anywhere: every segment is made
a safe file name by percent-encoding each byte outside ``[A-Za-z0-9._-]``
(``%`` itself included, so decoding is exact) and a leading ``.`` (so no
segment is a hidden or ``.git`` entry), and a ref with an empty, ``.`` or
``..`` segment is refused outright rather than encoded.

Machine-local refs — a proxy token unlocks only this machine's loopback model
proxy (``PROXY_TOKEN_REF_PREFIX``) — are filed under ``local/credentials/``,
which no commit and no sync round ever reads.
"""

from __future__ import annotations

import re
from urllib.parse import unquote_to_bytes

from coffer.domain.model_proxy.state import PROXY_TOKEN_REF_PREFIX

#: The ref families that are true of this machine only.
LOCAL_REF_PREFIXES: tuple[str, ...] = (PROXY_TOKEN_REF_PREFIX,)

SUFFIX = ".enc"

_SAFE = re.compile(r"[A-Za-z0-9._-]")


def is_local_ref(ref: str) -> bool:
    """Whether ``ref`` names machine-local ciphertext that never enters the vault."""
    return ref.startswith(LOCAL_REF_PREFIXES)


def _encode_segment(segment: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(segment):
        if _SAFE.fullmatch(ch) and not (i == 0 and ch == "."):
            out.append(ch)
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8"))
    return "".join(out)


def ref_to_relpath(ref: str) -> str:
    """The ``/``-separated path of ``ref``'s file, relative to a credentials dir.

    Raises ``ValueError`` for a ref with an empty, ``.`` or ``..`` segment.
    """
    segments = ref.split("/")
    if any(s in ("", ".", "..") for s in segments):
        raise ValueError(f"not a credential ref: {ref!r}")
    return "/".join(_encode_segment(s) for s in segments) + SUFFIX


def relpath_to_ref(relpath: str) -> str | None:
    """The ref a file at ``relpath`` holds, or None when it is not a ref file
    (another suffix, a hidden temp file, a name this module would not have
    written). Only the canonical encoding decodes, so one ref has one file."""
    if not relpath.endswith(SUFFIX):
        return None
    segments = relpath[: -len(SUFFIX)].split("/")
    decoded: list[str] = []
    for segment in segments:
        try:
            decoded.append(unquote_to_bytes(segment).decode("utf-8"))
        except UnicodeDecodeError:
            return None
    ref = "/".join(decoded)
    try:
        return ref if ref_to_relpath(ref) == relpath else None
    except ValueError:
        return None


__all__ = [
    "LOCAL_REF_PREFIXES",
    "SUFFIX",
    "is_local_ref",
    "ref_to_relpath",
    "relpath_to_ref",
]
