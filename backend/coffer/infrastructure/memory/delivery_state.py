"""Records, per agent, the moment Coffer's session-start hook last actually
fired (spec memory FR-055) — the one fact the removed injection layer
couldn't answer, because nothing recorded it.

A flat ``{agent_name: iso_timestamp}`` mapping, serialised as one JSON file
under :func:`coffer.infrastructure.memory.paths.memory_root`, exactly like
``source_state.py``'s digest cache. Dot-prefixed and derived: an agent that
has never fired simply has no key, and
``domain.memory.delivery.DeliveryStatus.last_fired_at`` reports ``""`` for it
— never a guess, never "unknown".
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime

from coffer.infrastructure.memory import paths

STATE_FILENAME = ".delivery_state.json"


def _state_path() -> pathlib.Path:
    return paths.memory_root() / STATE_FILENAME


def load() -> dict[str, str]:
    """The last-fired timestamp recorded for each agent, or ``{}``.

    Tolerant of a missing or corrupt file: losing this state only means
    ``last_fired_at`` reports never-fired again until the hook next runs —
    never a crash, and never a wrong answer in the other direction.
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


def last_fired_at(agent: str) -> str:
    """ISO-8601 UTC timestamp of `agent`'s last fire, or ``""`` if never."""
    return load().get(agent, "")


def record_fired(agent: str, *, now: datetime | None = None) -> None:
    """Record that `agent`'s hook just fired, at `now` (default: current UTC time)."""
    state = load()
    state[agent] = (now or datetime.now(UTC)).isoformat()
    save(state)
