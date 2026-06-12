"""Skill-location helpers for agent workspace scanning (FR-022).

``scan_locations`` returns the ordered list of directories to scan for
unmanaged skills for a given agent type.  It lives here (in the *agent*
domain, not the *skill* domain) because it depends on ``AgentType``, and
the import-linter contracts (Contract 5c in ``pyproject.toml``) forbid
``coffer.domain.skill`` from importing ``coffer.domain.agent``.

Infrastructure / application code that needs both scan-location resolution
and unmanaged-skill classification should import:
- ``scan_locations`` from this module, and
- ``classify`` from ``coffer.domain.skill.scan``.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.agent.types import AgentType


def _home() -> pathlib.Path:
    """Home dir — same ``os.environ`` pattern as ``config_files.py``."""
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


def scan_locations(
    agent_type: AgentType,
    config_dir: pathlib.Path,
    *,
    home: pathlib.Path | None = None,
) -> list[pathlib.Path]:
    """Ordered skill locations to scan for *agent_type* (FR-022).

    Args:
        agent_type: The agent product whose skill directories to resolve.
        config_dir: The agent's effective config root (e.g. ``~/.claude`` or
            ``~/.codex``).  Always the first source of ``<config_dir>/skills``.
        home: Override the home directory used for secondary locations.
            Defaults to ``$HOME`` (same env-read pattern as other domain
            modules).

    Returns:
        An ordered list of ``pathlib.Path`` values.  Paths need not exist —
        the infrastructure scanning layer handles missing-directory cases.

    Locations by agent type:
    - **CLAUDE_CODE**: ``[<config_dir>/skills]``
    - **CODEX**: ``[<config_dir>/skills, ~/.agents/skills]``
      The second entry (``~/.agents/skills``) is Codex's newer standard
      location introduced in later CLI versions; both must be scanned.
    """
    if home is None:
        home = _home()
    locs: list[pathlib.Path] = [config_dir / "skills"]
    if agent_type is AgentType.CODEX:
        locs.append(home / ".agents" / "skills")
    return locs
