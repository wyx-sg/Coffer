"""Memory triggers on disk: ``vault/memory-triggers/<id>.md`` (spec memory
"Keep triggers in the vault, armed only by a person").

One Markdown file per trigger — YAML frontmatter holding the note it names, its
kind and patterns, who proposed it and who armed it, and an optional body a
person may write as the reason to show when the note itself is gone. A plain
file so a person can read, edit or delete one with their own tools, and so the
vault's sync carries it like any other authored file.

A file that does not parse, or whose fields do not validate, is skipped by
:func:`list_triggers` (and logged) rather than failing every hook fire: a
trigger is advice, and one bad file must not stop the rest.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from coffer.domain.memory.trigger import Trigger, TriggerInvalid, TriggerNotFound, validate
from coffer.infrastructure.memory import paths
from coffer.infrastructure.memory.frontmatter import (
    atomic_write,
    render_frontmatter,
    split_frontmatter,
)

logger = logging.getLogger(__name__)

_FIELDS = (
    "id",
    "note",
    "kind",
    "command",
    "unless",
    "error",
    "armed_by",
    "armed_at",
    "proposed_by",
    "created",
)


def _path(trigger_id: str) -> pathlib.Path:
    paths.check_segment(trigger_id)
    return paths.triggers_root() / f"{trigger_id}.md"


def _parse(text: str, fallback_id: str) -> Trigger:
    fm, body = split_frontmatter(text)
    values: dict[str, Any] = {k: fm.get(k) for k in _FIELDS}
    fields = {k: ("" if v is None else str(v)) for k, v in values.items()}
    fields["id"] = fields["id"] or fallback_id
    return validate(Trigger(**fields, body=body.strip()))


def render(trigger: Trigger) -> str:
    """The file's text: every field in a fixed order, the body below."""
    fm = {k: getattr(trigger, k) for k in _FIELDS}
    body = f"{trigger.body.strip()}\n" if trigger.body.strip() else ""
    return render_frontmatter(fm, body)


def list_triggers() -> list[Trigger]:
    """Every trigger file that parses, by id."""
    root = paths.triggers_root()
    if not root.is_dir():
        return []
    out: list[Trigger] = []
    for path in sorted(root.glob("*.md")):
        try:
            out.append(_parse(path.read_text(encoding="utf-8"), path.stem))
        except (OSError, ValueError, TriggerInvalid) as e:
            logger.warning("memory.trigger.unreadable; path=%s error=%s", path, e)
    return out


def read_trigger(trigger_id: str) -> Trigger:
    """One trigger, or :class:`TriggerNotFound`."""
    path = _path(trigger_id)
    if not path.is_file():
        raise TriggerNotFound(f"no memory trigger {trigger_id!r}")
    return _parse(path.read_text(encoding="utf-8"), trigger_id)


def write_trigger(trigger: Trigger) -> pathlib.Path:
    """Write one trigger atomically, creating the directory on first use."""
    validate(trigger)
    path = _path(trigger.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, render(trigger))
    return path


def delete_trigger(trigger_id: str) -> None:
    """Remove one trigger's file, or :class:`TriggerNotFound`."""
    path = _path(trigger_id)
    if not path.is_file():
        raise TriggerNotFound(f"no memory trigger {trigger_id!r}")
    path.unlink()


__all__ = ["delete_trigger", "list_triggers", "read_trigger", "render", "write_trigger"]
