"""A run's uploaded inputs on disk (spec workflow "Store an uploaded
input under the run's directory").

An uploaded file lives under the run's own directory, beside the artifacts its
nodes will write, so a node reads it with the filesystem it already has rather
than through a second retrieval path. Its ``ref`` is the name relative to
``inputs/``, which is what the node's context quotes and what the API path
carries back on a delete.

**The filename is attacker-shaped input.** It arrives from a multipart upload,
which means it arrives from whatever the browser or the CLI was handed, and a
browser is free to send ``../../.ssh/authorized_keys`` or a Windows path with
backslashes in it. Two things happen before it reaches a path, in this order:

1. every directory part is discarded — a name is a NAME, so ``a/b/c.md``
   becomes ``c.md`` and ``../../x`` becomes ``x``, with backslashes folded to
   slashes first so a Windows-style path cannot smuggle a segment past it;
2. what is left goes through ``paths.check_segment``, the same guard every
   artifact name passes — empty, dots-only, hidden and separator-bearing names
   are refused rather than repaired, because a name this module had to invent
   is a name the developer did not upload.

``paths.input_path`` then re-runs the guard and resolves the result against the
run directory, so a symlinked ``inputs/`` cannot carry the write out of the
tree either. The guard is cheap and the failure it prevents is not.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.workflow import paths

__all__ = ["delete_input", "safe_input_name", "write_input"]


def safe_input_name(filename: str, *, taken: frozenset[str] = frozenset()) -> str:
    """The one path segment ``filename`` is allowed to become.

    ``taken`` are the refs the run already has. A second upload of ``prd.pdf``
    becomes ``prd-2.pdf`` rather than overwriting the first: the two are
    different documents the developer mounted on purpose, and removing one
    input must never take another's bytes with it.
    """
    bare = pathlib.PurePosixPath(filename.replace("\\", "/")).name
    paths.check_segment(bare)
    if bare not in taken:
        return bare
    stem = pathlib.PurePosixPath(bare).stem
    suffix = pathlib.PurePosixPath(bare).suffix
    counter = 2
    while True:
        candidate = f"{stem}-{counter}{suffix}"
        paths.check_segment(candidate)
        if candidate not in taken:
            return candidate
        counter += 1


def write_input(
    run_id: str,
    filename: str,
    content: bytes,
    *,
    taken: frozenset[str] = frozenset(),
) -> tuple[str, int, str]:
    """Store one upload and return ``(ref, size, absolute_path)``.

    ``ref`` is relative to the run's ``inputs/`` directory — never absolute,
    because it travels into the run's JSON column and into an API path, and
    neither should carry this machine's layout.

    The absolute path is returned beside it because the NODE needs a different
    answer than the API does: an upload lands in ``inputs/`` while a node runs
    in ``workspace/``, so a path relative to the working directory would have
    to climb out of it with ``..``, which some agents refuse. The node is told
    where the file actually is (spec workflow "Store an uploaded input under
    the run's directory").
    """
    name = safe_input_name(filename, taken=taken)
    target = paths.input_path(run_id, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return name, len(content), str(target)


def delete_input(run_id: str, ref: str) -> None:
    """Remove one uploaded input's bytes. Absent is success, not an error.

    ``ref`` goes through the same guard on the way in: it is read back out of a
    JSON column and off a URL path, so it is no more trusted here than the
    filename was.
    """
    target = paths.input_path(run_id, ref)
    if not target.is_symlink() and not target.is_file():
        # A directory, or nothing at all. Either way there is no uploaded file
        # here to remove, and this module does not delete trees.
        return
    # ``unlink`` removes a symlink itself rather than following it, so a link
    # somebody put under ``inputs/`` costs its target nothing.
    target.unlink()
