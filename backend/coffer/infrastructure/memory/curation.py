"""Each agent's own memory curation: whether it is on, and asking it to run
now (spec memory "Show each agent's own curation and ask it to curate now").

Read from the agents' own settings files, never from their internal
databases:

- Claude Code's auto memory: ``autoMemoryEnabled`` in ``settings.json``,
  absent meaning on. Auto Dream has no documented setting yet, so its state
  reads ``unknown`` with a hint to check ``/memory``.
- Codex's memories: ``[features] memories`` in ``config.toml``; Codex's
  consolidation runs whenever memories are on.

**Curate now** starts the agent without a terminal in the person's home
directory with a prompt asking it to consolidate its memory, and does not
wait for it: the agent's own curation is its business, and its result is the
agent's memory files.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
from dataclasses import dataclass

from coffer.domain.memory.hub import CLAUDE_CODE, CODEX
from coffer.infrastructure.memory.writers.codex import memories_enabled
from coffer.infrastructure.platform.user_path import which_on_user_path

logger = logging.getLogger(__name__)

ON = "on"
OFF = "off"
UNKNOWN = "unknown"

CURATE_PROMPT = (
    "Consolidate your memory files now: merge duplicates, drop what is "
    "contradicted or stale, and keep your index short. Change nothing else."
)

_BINARY = {CLAUDE_CODE: "claude", CODEX: "codex"}


@dataclass(frozen=True)
class CurationState:
    """Whether an agent's own memory, and its own curation, are on."""

    memory: str
    curation: str


def curation_state(agent_type: str, config_dir: str) -> CurationState:
    if agent_type == CLAUDE_CODE:
        memory = _claude_auto_memory(config_dir)
        return CurationState(memory=memory, curation=UNKNOWN if memory == ON else OFF)
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


def curate_command(agent_type: str, binary: str) -> list[str]:
    if agent_type == CLAUDE_CODE:
        return [binary, "-p", CURATE_PROMPT]
    return [binary, "exec", "--skip-git-repo-check", CURATE_PROMPT]


async def launch_curation(agent_type: str, config_dir: str, home: str) -> bool:
    """Start the agent headless in ``home`` with the curation prompt; answer
    whether it started. The process is not waited for."""
    binary = which_on_user_path(_BINARY.get(agent_type, ""))
    if binary is None:
        return False
    env = dict(os.environ)
    if agent_type == CLAUDE_CODE:
        env["CLAUDE_CONFIG_DIR"] = config_dir
    elif agent_type == CODEX:
        env["CODEX_HOME"] = config_dir
    try:
        await asyncio.create_subprocess_exec(
            *curate_command(agent_type, binary),
            cwd=home,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        logger.warning("memory.curation.launch_failed agent=%s", agent_type, exc_info=True)
        return False
    return True


__all__ = [
    "CURATE_PROMPT",
    "OFF",
    "ON",
    "UNKNOWN",
    "CurationState",
    "curate_command",
    "curation_state",
    "launch_curation",
]
