"""Pure managed-block text operations (spec 004, agent layer).

A *managed block* is a region of a text file fenced by a pair of marker lines
that a Coffer feature owns and rewrites idempotently, leaving every byte outside
the markers untouched. Instructions delivery (spec 004) keeps such a block in an
agent's instructions file, fenced by its own ``coffer:instructions`` markers, so
the managed region coexists with any other feature's content in the same file.

Side-effect-free core kept in the domain layer so the delivery service — and any
future managed-block writer — share one implementation.
"""

from __future__ import annotations


def upsert_block(text: str, body: str, *, start_marker: str, end_marker: str) -> str:
    """Return ``text`` with a managed block carrying ``body`` inserted or replaced.

    The block is ``{start_marker}\\n{body.rstrip()}\\n{end_marker}``. When the
    block is absent it is appended after the existing content (separated by a
    blank line); when present it is replaced in place. Content outside the
    markers is preserved byte-for-byte. A dangling start marker (no matching end)
    is replaced from the start marker to end of file.
    """
    block = f"{start_marker}\n{body.rstrip()}\n{end_marker}"
    start = text.find(start_marker)
    if start == -1:
        prefix = text.rstrip("\n")
        sep = "\n\n" if prefix else ""
        return f"{prefix}{sep}{block}\n"
    end = text.find(end_marker, start)
    if end == -1:
        # Dangling start marker — replace from the start marker to EOF.
        return text[:start] + block + "\n"
    end_full = end + len(end_marker)
    return text[:start] + block + text[end_full:]


def strip_block(text: str, *, start_marker: str, end_marker: str) -> str:
    """Return ``text`` with the managed block removed (and only it).

    Absent block → ``text`` is returned unchanged. The blank gap the block left
    behind is collapsed. A dangling start marker (no matching end) is trimmed to
    end of file.
    """
    start = text.find(start_marker)
    if start == -1:
        return text
    end = text.find(end_marker, start)
    if end == -1:
        return text[:start].rstrip("\n") + "\n"
    end_full = end + len(end_marker)
    before = text[:start].rstrip("\n")
    after = text[end_full:].lstrip("\n")
    if before and after:
        return f"{before}\n\n{after}"
    return (before or after).rstrip("\n") + ("\n" if (before or after) else "")


def extract_block(text: str, *, start_marker: str, end_marker: str) -> str | None:
    """Return the body inside the managed block, or ``None`` when absent.

    The body is the text between the marker lines with the fencing newlines
    stripped. A dangling start marker (no matching end) yields the text from the
    start marker to end of file.
    """
    start = text.find(start_marker)
    if start == -1:
        return None
    body_start = start + len(start_marker)
    end = text.find(end_marker, body_start)
    raw = text[body_start:] if end == -1 else text[body_start:end]
    return raw.strip("\n")


def has_block(text: str, *, start_marker: str) -> bool:
    """Whether a managed block opened by ``start_marker`` is present in ``text``."""
    return start_marker in text
