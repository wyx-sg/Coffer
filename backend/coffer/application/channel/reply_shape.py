"""Find the ``## Details`` section of a finished reply.

Spec channels "Shape a reply for what the chat can show". The agent is asked to
put long content under a ``## Details`` heading; :func:`split_details` finds it
so a transport can collapse it (Telegram) or move it to a card (SeaTalk).
Everything else in the reply goes to the platform renderer as the agent wrote it.

Pure: no I/O.
"""

from __future__ import annotations

import re

__all__ = ["split_details"]

_DETAILS_HEADING = re.compile(r"^#{1,3}[ \t]+details[ \t]*:?[ \t]*$", re.IGNORECASE | re.MULTILINE)


def split_details(markdown: str) -> tuple[str, str]:
    """``(head, details)``: the reply before its ``## Details`` heading and the
    section under it (heading removed); ``details`` is "" when there is none."""
    match = _DETAILS_HEADING.search(markdown)
    if match is None:
        return markdown, ""
    return markdown[: match.start()].rstrip(), markdown[match.end() :].strip()
