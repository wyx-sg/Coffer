"""The environment that points an agent's own runtime at its config directory.

Coffer delivers skills, installs its MCP entry and edits config files in the
agent's ``config_dir``. Any process Coffer spawns to *run* that agent — a chat
or channel turn, a ``model/list`` probe — must read the same directory, or it
reads the type's default one and never sees what Coffer put there.

Each product has exactly one way to be pointed elsewhere, named on its
descriptor (``home_env_var``): Claude Code reads ``CLAUDE_CONFIG_DIR`` (and
then keeps ``.claude.json`` inside that directory), Codex reads ``CODEX_HOME``
(its ``config.toml``, ``auth.json``, sessions and memories all live under it —
confirmed on codex-cli 0.155.1: a broken ``config.toml`` in ``$CODEX_HOME`` is
the one ``codex login status`` refuses to load). For the default directory
nothing is set, so the process behaves exactly as when the user runs the CLI
themselves — spec chat "Ship Claude Code and Codex subprocess providers".
"""

from __future__ import annotations

import pathlib

from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.types import AgentType


def _same_dir(a: pathlib.Path, b: pathlib.Path) -> bool:
    return a.expanduser().resolve() == b.expanduser().resolve()


def home_env(agent_type: AgentType, config_dir: pathlib.Path) -> dict[str, str]:
    """``{VAR: config_dir}`` for a non-default directory, ``{}`` for the default.

    Overrides only — a caller that spawns with a replaced (not merged)
    environment merges these over ``os.environ`` itself.
    """
    descriptor = descriptor_for(agent_type)
    if not descriptor.home_env_var:
        return {}
    if _same_dir(config_dir, descriptor.default_config_dir()):
        return {}
    return {descriptor.home_env_var: str(config_dir)}


__all__ = ["home_env"]
