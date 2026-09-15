"""On-disk layout for the derived state the agent layer keeps for itself.

The rest of this package only ever *reads* the agent's files — its config, its
plugins, its transcripts all belong to the agent, and Coffer writes none of
them. One thing does need somewhere to live, and it is not an agent file at
all: the transcript listing's summary sidecar, which is Coffer's own note of
what it already parsed. It gets its own root here rather than a corner of
someone else's tree.

The root is deliberately **outside the vault and outside ``coffer.db``**, per
the disposable-sidecar rule in ADR ``knowledge-is-plain-files``: nothing under
it is a truth, so nothing under it can drift. The user may delete it at any
moment, no export or backup carries it, and every reader of it must answer
correctly while it is missing, empty or mid-rebuild — it can only make an
answer faster, never different.

``$COFFER_AGENT_STATE_ROOT`` overrides the root, exactly like knowledge's and
memory's own overrides, and for the same reason: without it a test run writes
into the developer's real ``~/.coffer`` (a past bug did precisely that to the
knowledge tree with its override left unset).
"""

from __future__ import annotations

import os
import pathlib

#: Dot-prefixed and derived, like every other sidecar this codebase keeps
#: beside a tree rather than inside one.
TRANSCRIPT_SUMMARIES_FILENAME = ".transcript_summaries.json"


def agent_state_root() -> pathlib.Path:
    """The one directory the agent layer's own derived state lives in."""
    override = os.environ.get("COFFER_AGENT_STATE_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "cache" / "agent"


def transcript_summaries_path() -> pathlib.Path:
    """Where the transcript reader remembers what it already parsed."""
    return agent_state_root() / TRANSCRIPT_SUMMARIES_FILENAME
