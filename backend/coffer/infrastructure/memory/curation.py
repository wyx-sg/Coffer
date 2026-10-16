"""Each agent's own memory curation: whether it is on, and asking it to run
now (spec memory "Show each agent's own curation and ask it to curate now").

Read from the agents' own settings files, never from their internal
databases:

- Claude Code's auto memory: ``autoMemoryEnabled`` in ``settings.json``,
  absent meaning on. Auto Dream (its background consolidation) is not in
  Claude Code's documentation: ``autoDreamEnabled`` in ``settings.json``
  overrides a server default that Claude Code caches in its ``.claude.json``
  (``cachedGrowthBookFeatures.tengu_onyx_plover.enabled``). Either is read;
  neither present reads ``unknown``. A run leaves ``.consolidate-lock`` in
  the project's memory folder, whose newest time is when it last curated.
  **Turn on** writes ``autoDreamEnabled: true`` into ``settings.json``, backed
  up first, only when the person asks (ADR
  curate-claude-memory-in-the-open).
- Codex's memories: ``[features] memories`` in ``config.toml``; Codex's
  consolidation runs whenever memories are on.

**Curate now** is a hand-off (``application.memory.sync_view``): the
person watches the agent consolidate in a terminal.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.domain.memory.hub import CLAUDE_CODE, CODEX
from coffer.infrastructure.memory import native_files
from coffer.infrastructure.memory.writers.codex import memories_enabled

ON = "on"
OFF = "off"
UNKNOWN = "unknown"


#: Where a curation state came from: the agent's own setting, or the
#: default its vendor sets for the account.
SOURCE_SETTING = "setting"
SOURCE_DEFAULT = "default"

_AUTO_DREAM_KEY = "autoDreamEnabled"
_AUTO_DREAM_FLAG = "tengu_onyx_plover"
_LOCK_NAME = ".consolidate-lock"


@dataclass(frozen=True)
class CurationState:
    """Whether an agent's own memory, and its own curation, are on."""

    memory: str
    curation: str
    #: :data:`SOURCE_SETTING` or :data:`SOURCE_DEFAULT`; ``""`` when unknown.
    source: str = ""
    #: When the agent's curation last ran here (ISO 8601), ``""`` if never seen.
    last_curated_at: str = ""


def curation_state(agent_type: str, config_dir: str) -> CurationState:
    if agent_type == CLAUDE_CODE:
        memory = _claude_auto_memory(config_dir)
        if memory != ON:
            return CurationState(memory=memory, curation=OFF)
        curation, source = _claude_auto_dream(config_dir)
        return CurationState(
            memory=memory,
            curation=curation,
            source=source,
            last_curated_at=_claude_last_curated(config_dir),
        )
    if agent_type == CODEX:
        enabled = memories_enabled(config_dir)
        state = UNKNOWN if enabled is None else (ON if enabled else OFF)
        return CurationState(memory=state, curation=state)
    return CurationState(memory=UNKNOWN, curation=UNKNOWN)


def _claude_auto_memory(config_dir: str) -> str:
    path = pathlib.Path(config_dir) / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ON
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return UNKNOWN
    if not isinstance(data, dict):
        return UNKNOWN
    return OFF if data.get("autoMemoryEnabled") is False else ON


def _read_json(path: pathlib.Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _claude_global_config(config_dir: str) -> pathlib.Path:
    """Claude Code's ``.claude.json``: inside a ``CLAUDE_CONFIG_DIR``, or
    beside the default ``~/.claude``."""
    folder = pathlib.Path(config_dir)
    inside = folder / ".claude.json"
    if inside.is_file() or folder.name != ".claude":
        return inside
    return folder.parent / ".claude.json"


def _claude_auto_dream(config_dir: str) -> tuple[str, str]:
    settings = _read_json(pathlib.Path(config_dir) / "settings.json") or {}
    value = settings.get(_AUTO_DREAM_KEY)
    if isinstance(value, bool):
        return (ON if value else OFF), SOURCE_SETTING
    cached = _read_json(_claude_global_config(config_dir)) or {}
    features = cached.get("cachedGrowthBookFeatures")
    flag = features.get(_AUTO_DREAM_FLAG) if isinstance(features, dict) else None
    enabled = flag.get("enabled") if isinstance(flag, dict) else None
    if isinstance(enabled, bool):
        return (ON if enabled else OFF), SOURCE_DEFAULT
    return UNKNOWN, ""


def _claude_last_curated(config_dir: str) -> str:
    newest = 0.0
    for lock in (pathlib.Path(config_dir) / "projects").glob(f"*/memory/{_LOCK_NAME}"):
        try:
            newest = max(newest, lock.stat().st_mtime)
        except OSError:
            continue
    if not newest:
        return ""
    return datetime.fromtimestamp(newest, tz=UTC).isoformat().replace("+00:00", "Z")


def enable_curation(agent_type: str, config_dir: str) -> bool:
    """Turn the agent's own curation on in its settings, backed up first;
    answer whether anything was written. Only Claude Code's Auto Dream has a
    switch: Codex's consolidation runs whenever its memories are on."""
    if agent_type != CLAUDE_CODE:
        return False
    path = pathlib.Path(config_dir) / "settings.json"
    current = native_files.read(path)
    settings: dict[str, object] = {}
    if current is not None and current.strip():
        loaded = json.loads(current)
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} does not hold a JSON object")
        settings = loaded
    if settings.get(_AUTO_DREAM_KEY) is True:
        return False
    settings[_AUTO_DREAM_KEY] = True
    mode = path.stat().st_mode & 0o777 if path.exists() else None
    native_files.backup(path)
    native_files.write(path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    if mode is not None:
        path.chmod(mode)
    return True


__all__ = [
    "OFF",
    "ON",
    "SOURCE_DEFAULT",
    "SOURCE_SETTING",
    "UNKNOWN",
    "CurationState",
    "curation_state",
    "enable_curation",
]
