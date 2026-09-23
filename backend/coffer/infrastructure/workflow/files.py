"""Reading one file out of a run's directory, for the UI's preview (spec
workflow "Read a run's files from the app, bounded").

The context table lists what a run reads and what it wrote; this is what makes
a row openable. Reading and nothing else: no write here, no listing, no
traversal — one path, guarded segment by segment against the same rules every
other path in this layer goes through, and refused if it resolves outside the
run even by way of a symlink.

Two bounds, both deliberate:

* A **size cap**. A preview is a thing a person reads, and a task can produce
  a 200MB log; sending it to a browser would hang the tab rather than show
  anything. The head of the file is returned and the answer says it is a head.
* **Text only.** Bytes that are not UTF-8 come back with no text and the size
  they have, because rendering a PNG as mojibake would claim to have shown the
  developer something.

``read_bytes`` is the other half of that last bound rather than an exception to
it: a screenshot pasted into a note ("Keep the developer's own notes in a run's
context") is not text and must still be shown, so it is served AS an image —
with a media type taken from the name and narrowed to a list this module is
willing to hand a browser, because a file a run produced is not a file a
browser should be free to interpret.
"""

from __future__ import annotations

import dataclasses
import pathlib

from coffer.infrastructure.workflow import paths

#: What a preview returns at most. Generous for a document, small enough that
#: no single response is a problem.
MAX_PREVIEW_BYTES = 256 * 1024


@dataclasses.dataclass(frozen=True)
class RunFile:
    """One file under a run's directory, as the API reports it."""

    #: The path as it was asked for, relative to the run directory.
    path: str
    name: str
    #: The file's real size, not the size of what came back.
    size: int
    #: ``None`` when the bytes are not UTF-8 text.
    text: str | None
    #: True when ``text`` is the head of a longer file.
    truncated: bool


#: What ``read_bytes`` is willing to name as a media type. Everything else is
#: served as an opaque download: a run's directory holds whatever its agent
#: wrote, and a browser handed ``text/html`` from it would run that file's
#: script against this app's origin.
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
    ".pdf": "application/pdf",
}

#: ``image/svg+xml`` is deliberately absent from what is rendered inline: an
#: SVG is a document that can carry script, so it is downloaded rather than
#: displayed, and the one place it could run is not this app's origin.
_SCRIPTABLE = {".svg"}


def resolve(run_id: str, rel_path: str) -> pathlib.Path:
    """The absolute path ``rel_path`` names inside ``run_id``'s directory.

    Every segment goes through ``check_segment``, so ``..``, a hidden entry and
    an absolute path are all refused before anything touches the disk; the
    assembled path is then checked against the run root, which is what catches
    a symlink pointing out of the tree.
    """
    normalised = rel_path.replace("\\", "/")
    # Refused rather than reinterpreted: silently treating `/etc/passwd` as a
    # path inside the run would answer "not found" to a question nobody meant
    # to ask, and hide the caller's bug behind a 404.
    if normalised.startswith("/"):
        raise paths.UnsafeWorkflowPath(rel_path, "absolute paths are not addressable")
    segments = [segment for segment in normalised.split("/") if segment != ""]
    if not segments:
        raise paths.UnsafeWorkflowPath(rel_path, "empty path")
    for segment in segments:
        paths.check_segment(segment)
    candidate = paths.run_dir(run_id).joinpath(*segments)
    paths.assert_inside_run(candidate, run_id)
    return candidate


def read_file(run_id: str, rel_path: str) -> RunFile | None:
    """``rel_path`` inside the run, or ``None`` when there is no such file."""
    target = resolve(run_id, rel_path)
    if not target.is_file():
        return None
    size = target.stat().st_size
    head = target.read_bytes()[: MAX_PREVIEW_BYTES + 1]
    truncated = len(head) > MAX_PREVIEW_BYTES
    try:
        text: str | None = head[:MAX_PREVIEW_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        # A truncated read can split a multi-byte character, so a decode error
        # on a capped head is not proof the file is binary — but an uncapped
        # one is, and the capped case degrades to "no preview" either way.
        text = None
    return RunFile(
        path="/".join(segment for segment in rel_path.split("/") if segment),
        name=target.name,
        size=size,
        text=text,
        truncated=truncated,
    )


def read_bytes(run_id: str, rel_path: str) -> tuple[bytes, str] | None:
    """``(bytes, media_type)`` for one file, or ``None`` when it is absent.

    Capped like the preview: an image a person pasted into a note is small, and
    a route that would stream a 200MB core dump into a browser tab because the
    path happened to resolve is a route that can be asked to.
    """
    target = resolve(run_id, rel_path)
    if not target.is_file():
        return None
    suffix = target.suffix.lower()
    media = _MEDIA_TYPES.get(suffix, "application/octet-stream")
    if suffix in _SCRIPTABLE:
        media = "application/octet-stream"
    return target.read_bytes()[:MAX_PREVIEW_BYTES], media
