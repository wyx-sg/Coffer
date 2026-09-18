"""Where the file-backed trees a round mirrors actually live (spec vault-sync).

A round mirrors the knowledge and skill trees in both directions. Their roots
are resolved here — not imported from the kind modules — so the sync slice
stays decoupled from every kind (cross-kind import fence) while honouring the
same ``$COFFER_*_ROOT`` overrides the kinds use.

The same file also names the one subtree inside them that a round leaves
alone, for the same reason and with the same deliberate duplication of a
literal (see :data:`NON_CONVERGING_TREE_PATHS`).
"""

from __future__ import annotations

import os
import pathlib


def _expand_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser()


def _rooted(env_var: str, *segments: str) -> pathlib.Path:
    override = os.environ.get(env_var)
    if override:
        return pathlib.Path(override).expanduser()
    return _expand_home().joinpath(".coffer", *segments)


def knowledge_root() -> pathlib.Path:
    """``~/.coffer/knowledge/`` (override ``$COFFER_KNOWLEDGE_ROOT``)."""
    return _rooted("COFFER_KNOWLEDGE_ROOT", "knowledge")


def skills_root() -> pathlib.Path:
    """``~/.coffer/skills/`` — the canonical skill master store."""
    return _rooted("COFFER_SKILLS_ROOT", "skills")


#: The file-backed trees a round mirrors, as (tree-subdir, live-root) pairs.
def mirrored_trees() -> list[tuple[str, pathlib.Path]]:
    return [
        ("knowledge", knowledge_root()),
        ("skills", skills_root()),
    ]


#: Bundle-relative directory prefixes a round neither publishes nor applies —
#: files inside the mirrored trees that are **derived output**, regenerated on
#: each machine rather than received from another (spec vault-sync FR-093).
#:
#: ``skills/coffer-guide/`` is Coffer's own generated skill. Its bytes are a
#: function of the running build, the knowledge files (which converge on their
#: own) and this machine's own reach — which collections are enabled, and that
#: is machine-local by FR-014. Two machines that agree about every file still
#: render different text, so mirroring it has them overwriting each other and
#: re-rendering forever.
#:
#: The name is a literal here, exactly as the roots above are literals. The
#: sync slice may not import ``coffer.domain.skill`` or
#: ``coffer.application.knowledge`` (import-linter's cross-kind fences), and
#: the module that does own the name is the renderer that writes it into the
#: skill's frontmatter. ``tests/contract/test_non_converging_tree_paths.py``
#: pins the two spellings together so they cannot drift apart in silence.
NON_CONVERGING_TREE_PATHS = frozenset({"skills/coffer-guide/"})


def non_converging_tree_paths() -> frozenset[str]:
    """:data:`NON_CONVERGING_TREE_PATHS`, as a call so every construction site
    reads it the same way the roots above are read."""
    return NON_CONVERGING_TREE_PATHS
