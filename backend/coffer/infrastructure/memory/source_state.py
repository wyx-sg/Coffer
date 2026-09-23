"""Remembers each source file's digest across aggregation passes.

See spec memory "Skip unchanged sources".

A source whose content hash matches what was recorded last time is not worth
re-parsing: the raw entries it produced are already sitting under the
partition's ``.raw/``, unchanged. That decision needs exactly one thing per
source — its last-seen digest — so this is a flat ``{native_path: digest}``
mapping, serialised as one JSON file under
:func:`coffer.infrastructure.memory.paths.memory_root`.

The layout change from ``facts/`` to ``notes/`` plus ``.raw/`` leaves this
module's job untouched, because it was never about the output: it answers "has
this *source* changed", and the sources are the agents' own files.

**A digest match is not on its own a reason to skip.** It says the source has
not changed; it does not say the entries it produced are still on disk, and
"Keep the memory tree derived and local" requires that deleting the memory tree
and re-syncing rebuilds the partition *with this cache deliberately left
behind*. So a caller combines the match with the presence of what it produced,
and the cost of this file being lost or stale is only a pass of unnecessary
re-parsing, never a partition that silently stays empty. Dot-prefixed and
derived like everything else the layer keeps outside the partition tree, and
never addressed through the partition path helpers in ``paths.py``, so it does
not need their traversal guard.
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

    Tolerant of a missing or corrupt file — losing this state only costs a pass
    of unnecessary re-parsing, never correctness (the whole point of "Keep the
    memory tree derived and local"). A source absent from the mapping has simply
    never been seen, which is the same instruction as "read it".
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
