"""A run's artifacts on disk — written, listed and read (FR-041, FR-031).

The tree is the attribution: ``artifacts/<node_key>/<attempt>/<name>``, so
which node and which attempt produced a file is a fact about where it is, not
a row that could drift from it. That is what makes the catalogue safe to
generate from the directory and safe to delete — the next regeneration
reproduces it (FR-031).

Nothing here indexes, chunks or embeds anything (FR-042): the files are the
only copy, and the reader is ``ripgrep`` or the agent that opens them.

The catalogue *text* is not written here. This module computes what it says —
the entries, attributed and dated — and the application layer renders the
Markdown, because how a catalogue reads to an agent is a question about
prompts, not about storage.
"""

from __future__ import annotations

import pathlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.infrastructure.workflow import paths


@dataclass(frozen=True)
class ArtifactEntry:
    """One artifact, with the node and attempt that produced it.

    ``path`` is relative to the run's artifact root, which is what the API
    reports and what a catalogue line quotes — an absolute path would leak the
    machine's layout into a document that travels to an agent's context.
    """

    name: str
    node_key: str
    attempt: int
    path: str
    size: int
    modified_at: datetime


def ensure_run_dirs(run_id: str) -> pathlib.Path:
    """Create the run's directory and its three fixed children, and return it.

    ``workspace/`` is one of them because Coffer assigns a run its working
    directory rather than being handed one, and a node's conversation cannot
    start in a directory that does not exist yet.
    """
    run = paths.run_dir(run_id)
    paths.inputs_dir(run_id).mkdir(parents=True, exist_ok=True)
    paths.artifacts_dir(run_id).mkdir(parents=True, exist_ok=True)
    paths.workspace_dir(run_id).mkdir(parents=True, exist_ok=True)
    return run


def write_artifact(
    run_id: str,
    node_key: str,
    attempt: int,
    name: str,
    content: bytes | str,
) -> pathlib.Path:
    """Write one artifact for ``(node_key, attempt)`` and return where it landed.

    A write to an attempt that already holds that name replaces it — an agent
    correcting its own output inside one attempt is ordinary. What is never
    replaced is another *attempt's* copy: that lives under its own number.
    """
    target = paths.artifact_path(run_id, node_key, attempt, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    return target


def read_artifact(run_id: str, node_key: str, attempt: int, name: str) -> bytes:
    """The bytes of one artifact. Raises ``FileNotFoundError`` when absent."""
    return paths.artifact_path(run_id, node_key, attempt, name).read_bytes()


def list_artifacts(run_id: str) -> list[ArtifactEntry]:
    """Every artifact the run has produced, attributed and ordered.

    Ordered by node, then attempt, then name, so a catalogue regenerated twice
    from the same directory is byte-identical — a file listing whose order came
    from the filesystem would make the catalogue churn for no reason and turn
    every regeneration into a visible change.

    A directory whose name is not a positive integer is skipped rather than
    guessed at: the tree is Coffer's own, so anything else in it was put there
    by something that is not this module, and inventing an attempt number for
    it would attribute a file to a try that never happened.
    """
    root = paths.artifacts_dir(run_id)
    if not root.is_dir():
        return []
    entries: list[ArtifactEntry] = []
    for node_path in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        node_key = paths.decode_node_dir(node_path.name)
        numbered = [
            (number, p)
            for p in node_path.iterdir()
            if p.is_dir() and not p.is_symlink() and (number := _attempt_of(p.name)) is not None
        ]
        for attempt, attempt_path in sorted(numbered, key=lambda pair: pair[0]):
            entries.extend(_files_in(run_id, node_key, attempt, attempt_path))
    return entries


def collect_artifacts(run_id: str, destination: pathlib.Path) -> int:
    """Copy every artifact into ``destination``, and say how many landed.

    This is the mechanical half of promotion (FR-043): the run directory is
    left exactly as it was, and the copy is flat and self-describing, because
    the collection that receives it has its own shape and nobody reading it
    later would recognise ``3/`` as an attempt number. Two attempts at the same
    name therefore keep both — the attempt is folded into the copied filename
    rather than one overwriting the other.
    """
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for entry in list_artifacts(run_id):
        source = paths.artifact_path(run_id, entry.node_key, entry.attempt, entry.name)
        stem = pathlib.Path(entry.name).stem
        suffix = pathlib.Path(entry.name).suffix
        safe_node = entry.node_key.replace(":", "-")
        shutil.copy2(source, destination / f"{safe_node}-{entry.attempt}-{stem}{suffix}")
        copied += 1
    return copied


def _attempt_of(name: str) -> int | None:
    """The attempt number a directory name stands for, or ``None`` if it is not one."""
    if not name.isdigit():
        return None
    value = int(name)
    return value if value >= 1 else None


def _files_in(
    run_id: str,
    node_key: str,
    attempt: int,
    attempt_path: pathlib.Path,
) -> list[ArtifactEntry]:
    """The artifacts of one attempt.

    Only regular files at this level are artifacts. A symlink is skipped: its
    target is outside what this layer controls, and a catalogue that named it
    would report a size and a date belonging to a file the run never wrote.
    """
    found: list[ArtifactEntry] = []
    for file_path in sorted(attempt_path.iterdir()):
        if file_path.is_symlink() or not file_path.is_file():
            continue
        stat = file_path.stat()
        found.append(
            ArtifactEntry(
                name=file_path.name,
                node_key=node_key,
                attempt=attempt,
                path=paths.relative_of(file_path, run_id),
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )
    return found
