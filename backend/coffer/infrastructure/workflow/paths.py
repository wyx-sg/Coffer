"""On-disk layout for a workflow run — the sole owner of path construction.

Mirrors ``infrastructure/knowledge/paths.py`` and ``infrastructure/memory/
paths.py`` on purpose: one root, one guard, one override for tests. The tree
is the one [`data-model.md`](../../../../specs/workflow/data-model.md) draws::

    ~/.coffer/workflows/<run_id>/
    ├── CATALOG.md                 # generated, never hand-edited (FR-031)
    ├── inputs/                    # uploaded files (FR-032)
    ├── workspace/                 # the run's working directory (FR-011)
    └── artifacts/<node_key>/<attempt>/<name>

``$COFFER_WORKFLOW_ROOT`` overrides the root. **Unset, it resolves to the
developer's real vault** — the hazard ``quickstart.md`` records — so every
test in this layer pins it, exactly as the knowledge and memory layers' own
tests do after one of them once rewrote a real tree.

Two kinds of untrusted string reach a path here. A ``run_id`` is a UUIDv4 the
system minted, and a ``node_key`` comes from a template the developer wrote —
including the ``adhoc:<slug>`` form an unplanned task carries (FR-028), whose
colon is not a legal path segment. ``encode_node_key`` percent-encodes that
one character and nothing else; because the segment guard refuses a raw ``%``,
the encoding is unambiguous and ``decode_node_dir`` inverts it exactly.
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.error_base import CofferError
from coffer.domain.workflow.run import ADHOC_KEY_PREFIX

CATALOG_NAME = "CATALOG.md"
INPUTS_DIR_NAME = "inputs"
ARTIFACTS_DIR_NAME = "artifacts"
WORKSPACE_DIR_NAME = "workspace"

#: How the one illegal character in an ``adhoc:`` key is spelled on disk. A raw
#: ``%`` never passes ``check_segment``, so no genuine key can impersonate an
#: encoded one and the mapping is a bijection.
_COLON_ESCAPE = "%3A"

_DOTS_ONLY = re.compile(r"^\.+$")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._\- 一-鿿]+$")


class UnsafeWorkflowPath(CofferError):  # noqa: N818
    """A path segment that is empty, hidden, all dots, or otherwise unsafe."""

    code = "WORKFLOW_UNSAFE_PATH"

    def __init__(self, segment: str, reason: str) -> None:
        super().__init__(f"unsafe workflow path segment {segment!r}: {reason}")
        self.segment = segment
        self.reason = reason


def workflow_root() -> pathlib.Path:
    """The one directory a run's files live under."""
    override = os.environ.get("COFFER_WORKFLOW_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "workflows"


def check_segment(segment: str) -> None:
    """Refuse a path component that is hidden, all dots, or otherwise unsafe.

    Defence in depth, per the same rule the other two file layers follow: a run
    id is minted by the system and an artifact name is validated at template
    write time, but neither fact is visible from here, and a path built from a
    template's contents is a path built from user input.
    """
    if not segment:
        raise UnsafeWorkflowPath(segment, "empty path segment")
    if _DOTS_ONLY.fullmatch(segment):
        raise UnsafeWorkflowPath(segment, "traversal segment")
    if segment.startswith("."):
        raise UnsafeWorkflowPath(segment, "hidden entries are not addressable")
    if not _SAFE_SEGMENT.fullmatch(segment):
        raise UnsafeWorkflowPath(segment, "unsafe segment")


def check_node_key(node_key: str) -> None:
    """Refuse a node key that could not be spelled as one directory name.

    A template node key is a plain segment. An ad-hoc task's key is
    ``adhoc:<slug>``, whose colon is the single exception this module knows how
    to encode — so the prefix is stripped and the remainder guarded like any
    other segment. Anything else with a colon in it is refused rather than
    quietly mangled.
    """
    if node_key.startswith(ADHOC_KEY_PREFIX):
        check_segment(node_key[len(ADHOC_KEY_PREFIX) :])
        return
    check_segment(node_key)


def encode_node_key(node_key: str) -> str:
    """The directory name for ``node_key`` — guarded, then colon-escaped."""
    check_node_key(node_key)
    return node_key.replace(":", _COLON_ESCAPE)


def decode_node_dir(dir_name: str) -> str:
    """The node key a directory name stands for — the inverse of the above."""
    return dir_name.replace(_COLON_ESCAPE, ":")


def check_attempt(attempt: int) -> None:
    """Attempts count from 1; anything else is a programming error, not a path."""
    if attempt < 1:
        raise UnsafeWorkflowPath(str(attempt), "attempt numbers start at 1")


def run_dir(run_id: str) -> pathlib.Path:
    """Everything one run owns on disk."""
    check_segment(run_id)
    return workflow_root() / run_id


def catalog_path(run_id: str) -> pathlib.Path:
    """The generated catalogue (FR-031). The text itself is written elsewhere."""
    return run_dir(run_id) / CATALOG_NAME


def inputs_dir(run_id: str) -> pathlib.Path:
    """Where a run's mounted uploads land (FR-032)."""
    return run_dir(run_id) / INPUTS_DIR_NAME


def workspace_dir(run_id: str) -> pathlib.Path:
    """The working directory every node conversation of this run runs in.

    Coffer assigns it rather than asking for one: creating a run is
    ``{template, title}`` and nothing else, and a run that has to be told where
    to work is a run the developer has to think about a path for before they
    have thought about the work. It lives under the run's own directory, beside
    the inputs the run reads and the artifacts it writes, so deleting the run
    takes its workspace with it.
    """
    return run_dir(run_id) / WORKSPACE_DIR_NAME


def artifacts_dir(run_id: str) -> pathlib.Path:
    """The root of the per-node, per-attempt artifact tree (FR-041)."""
    return run_dir(run_id) / ARTIFACTS_DIR_NAME


def node_dir(run_id: str, node_key: str) -> pathlib.Path:
    """One node's artifacts, across every attempt of it."""
    return artifacts_dir(run_id) / encode_node_key(node_key)


def attempt_dir(run_id: str, node_key: str, attempt: int) -> pathlib.Path:
    """One attempt's artifacts.

    A retry never rewrites an earlier attempt (FR-022), so the attempt number
    is part of the path rather than a version inside a file.
    """
    check_attempt(attempt)
    return node_dir(run_id, node_key) / str(attempt)


def artifact_path(run_id: str, node_key: str, attempt: int, name: str) -> pathlib.Path:
    """One artifact file. ``name`` is a single segment, per the template rule."""
    check_segment(name)
    candidate = attempt_dir(run_id, node_key, attempt) / name
    assert_inside_run(candidate, run_id)
    return candidate


def workspace_path(run_id: str, name: str) -> pathlib.Path:
    """One entry directly inside the run's working directory.

    Where a mounted repository's checkout lands (FR-057). ``name`` is a single
    segment derived from the source path's own basename, so it is user input
    like any other and goes through the same guard.
    """
    check_segment(name)
    candidate = workspace_dir(run_id) / name
    assert_inside_run(candidate, run_id)
    return candidate


def input_path(run_id: str, name: str) -> pathlib.Path:
    """One mounted input file."""
    check_segment(name)
    candidate = inputs_dir(run_id) / name
    assert_inside_run(candidate, run_id)
    return candidate


def _anchor(candidate: pathlib.Path) -> pathlib.Path:
    """The nearest part of ``candidate`` that is already on disk.

    A symlink counts even when it dangles: it is the thing a later write would
    follow, so it is the thing whose target has to be checked.
    """
    for part in (candidate, *candidate.parents):
        if part.is_symlink() or part.exists():
            return part
    return candidate


def assert_inside_run(candidate: pathlib.Path, run_id: str) -> None:
    """Refuse a path that resolves outside the run's own directory.

    The segment guard alone cannot see a symlink: a directory inside the run
    that points elsewhere would carry a write out of the tree, and the file
    being written does not exist yet, so the check runs on the nearest existing
    ancestor — which does.
    """
    root = run_dir(run_id)
    if not root.exists():
        return
    if not _anchor(candidate).resolve().is_relative_to(root.resolve()):
        raise UnsafeWorkflowPath(str(candidate), "escapes the run directory")


def relative_of(path: pathlib.Path, run_id: str) -> str:
    """The artifact-root-relative form the API reports (``ArtifactOut.path``)."""
    try:
        return str(path.relative_to(artifacts_dir(run_id)))
    except ValueError:
        return str(path)
