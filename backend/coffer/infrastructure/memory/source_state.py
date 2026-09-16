"""Remembers each source file's digest across aggregation passes (FR-006).

A source whose content hash matches what was recorded last time is not worth
re-parsing: its facts are already sitting on disk, unchanged. That decision
needs exactly one fact per source — its last-seen digest — so this is a flat
``{native_path: digest}`` mapping, serialised as one JSON file under
:func:`coffer.infrastructure.memory.paths.memory_root`.

Dot-prefixed and derived, like everything else this layer keeps outside the
partition tree proper: deleting it is safe (the next pass just re-parses
everything and gets the same facts back, per FR-016) and it is never addressed
through the partition path helpers in ``paths.py``, so it does not need their
traversal guard.
"""

from __future__ import annotations

import json
import pathlib

from coffer.infrastructure.memory import paths

STATE_FILENAME = ".source_state.json"


def _state_path() -> pathlib.Path:
    return paths.memory_root() / STATE_FILENAME


def load() -> dict[str, str]:
    """The digest recorded for each native path last pass, or ``{}``.

    Tolerant of a missing or corrupt file — losing this state only costs a
    pass of unnecessary re-parsing, never correctness (FR-016's whole point).
    """
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save(state: dict[str, str]) -> None:
    """Replace the recorded state with ``state``, atomically."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
