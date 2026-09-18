"""Reading one serialized document off the worktree.

Two appliers parse YAML — the resource applier and the state applier — so the
reader sits beside them rather than inside either. Its whole job is to turn
every way a file can fail to be a document (unreadable, not YAML, not a
mapping) into the one error the round knows how to hold a path for.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping

import yaml

from coffer.domain.sync.errors import SyncSerializationError


def read_yaml(path: pathlib.Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as e:
        raise SyncSerializationError(f"{path.name} could not be read: {e}") from e
    if not isinstance(raw, Mapping):
        raise SyncSerializationError(f"{path.name} is not a mapping")
    return dict(raw)
