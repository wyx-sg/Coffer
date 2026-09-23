"""Field-level coercion for a template config (spec workflow "Refuse an invalid
template naming the offending path").

Split out of :mod:`coffer.domain.workflow.template` for the file-size ceiling,
and it is the natural seam: everything here answers "is this scalar the right
shape?" and knows nothing about stages or the tasks in them. Every refusal names the
JSON path it was given, which is how the path in ``TemplateInvalid`` ends up
being the real one rather than an approximation assembled at the top.

Nothing here imports the template's own value objects, so the dependency runs
one way and the two modules cannot become a cycle.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from coffer.domain.workflow.errors import TemplateInvalid

#: Stage and node keys are lowercase slugs. A node key is additionally a path
#: segment on disk (``artifacts/<node_key>/<attempt>/``) and a bare identifier
#: in an event payload, so one pattern guards both: no separators, no colon
#: (which would collide with the ``adhoc:`` namespace), nothing exotic.
KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
KEY_MAX_LEN = 64


def as_object(raw: Any, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TemplateInvalid(path or "<root>", "must be an object")
    return raw


def reject_unknown(obj: dict[str, Any], allowed: set[str], path: str) -> None:
    """Refuse a field the engine would ignore.

    A silently-ignored ``artifact`` (for ``artifacts``) is a template that runs
    and quietly owes nothing — exactly the stalled run template validation
    exists to stop.
    """
    for name in sorted(obj):
        if name not in allowed:
            prefix = f"{path}." if path else ""
            raise TemplateInvalid(f"{prefix}{name}", "unknown field")


def as_key(raw: Any, path: str) -> str:
    value = as_required_str(raw, path)
    if len(value) > KEY_MAX_LEN:
        raise TemplateInvalid(path, f"too long ({len(value)} chars, max {KEY_MAX_LEN})")
    if not KEY_PATTERN.match(value):
        raise TemplateInvalid(path, "must be a lowercase slug (a-z, 0-9, '_' or '-')")
    return value


def as_artifact_name(raw: Any, path: str) -> str:
    """One path segment, because it becomes a file under the run's artifact
    directory and nothing else."""
    value = as_required_str(raw, path)
    if "/" in value or "\\" in value:
        raise TemplateInvalid(path, "must be a single path segment, with no separators")
    if set(value) == {"."}:
        raise TemplateInvalid(path, "must not be dots only")
    # `paths.py` refuses a hidden segment when it builds the artifact path, so
    # accepting one here would store a template that stalls the moment a node
    # tries to write it — which is the one thing template validation forbids.
    if value.startswith("."):
        raise TemplateInvalid(path, "must not start with '.'")
    return value


def as_required_str(raw: Any, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise TemplateInvalid(path, "must be a non-empty string")
    return raw.strip()


def as_optional_str(raw: Any, path: str) -> str | None:
    if raw is None:
        return None
    return as_required_str(raw, path)


def as_bool(raw: Any, path: str, *, default: bool) -> bool:
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise TemplateInvalid(path, "must be a boolean")
    return raw


def as_int(raw: Any, path: str) -> int:
    # bool is an int in Python; accepting `true` as 1 here would let a typo
    # through as a number.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TemplateInvalid(path, "must be an integer")
    return raw


def as_enum[E: StrEnum](enum_cls: type[E], raw: Any, path: str, *, default: E | None = None) -> E:
    if raw is None and default is not None:
        return default
    if not isinstance(raw, str):
        raise TemplateInvalid(path, f"must be one of: {', '.join(m.value for m in enum_cls)}")
    try:
        return enum_cls(raw)
    except ValueError:
        raise TemplateInvalid(
            path, f"must be one of: {', '.join(m.value for m in enum_cls)}"
        ) from None


def as_attempt_ceiling(raw: Any, path: str, *, default: int) -> int:
    """The cap on how many attempts one task may open (spec workflow "Bound
    each task's attempts by its own ceiling").

    Absent means the default rather than "no ceiling" — a task without one is
    a task that can loop all night. ``path`` names the task, because that is
    now where the number lives: there is no run-wide ceiling to fall back on,
    and a refusal that said only ``attempt_ceiling`` would not say which of a
    template's twelve tasks was wrong.
    """
    if raw is None:
        return default
    value = as_int(raw, path)
    if value < 1:
        raise TemplateInvalid(path, "must be >= 1")
    return value
