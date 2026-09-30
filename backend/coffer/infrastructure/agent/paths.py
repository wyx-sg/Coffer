"""On-disk layout for the derived state the agent layer keeps for itself.

The rest of this package only ever *reads* the agent's files — its config, its
plugins, its transcripts all belong to the agent, and Coffer writes none of
them. One thing does need somewhere to live, and it is not an agent file at
all: the transcript listing's summary sidecar, which is Coffer's own note of
what it already parsed. It gets its own root here rather than a corner of
someone else's tree.

The root is ``~/.coffer/derived/cache/agent`` — the ``derived`` class of ADR
storage-is-five-classes-by-nature: nothing under it is a truth, so nothing
under it can drift. The user may delete it at any moment, nothing syncs or
backs it up, and every reader of it must answer correctly while it is missing,
empty or mid-rebuild — it can only make an answer faster, never different.
There is no override: it is resolved from ``HOME`` at every call, which is how
a test's throwaway home keeps it off the developer's real ``~/.coffer``.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.vault.home import derived_root

#: Dot-prefixed and derived, like every other sidecar this codebase keeps
#: beside a tree rather than inside one.
TRANSCRIPT_SUMMARIES_FILENAME = ".transcript_summaries.json"


def agent_state_root() -> pathlib.Path:
    """The one directory the agent layer's own derived state lives in."""
    return derived_root() / "cache" / "agent"


def transcript_summaries_path() -> pathlib.Path:
    """Where the transcript reader remembers what it already parsed."""
    return agent_state_root() / TRANSCRIPT_SUMMARIES_FILENAME
