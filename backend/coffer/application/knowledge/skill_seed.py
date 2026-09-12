"""Ship the knowledge skill into Coffer's own skill store at boot.

This is the layer's delivery half (spec knowledge FR-042). Knowledge reaches a
session only when an agent asks for it, and the audit that led to this design
found agents never ask on their own: a tool's own description does not make a
model remember the tool exists. A skill does — its name and description sit in
the agent's context, and Coffer already delivers skills into every managed
agent's skill directory, so this reuses a channel known to work rather than
installing a hook or writing into anyone's memory files.

Seeding is idempotent: the bundled folder is re-imported on every boot, so an
edit to the asset ships with the next daemon start, and a user who deleted the
skill gets it back.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

SKILL_NAME = "coffer-knowledge"
_ASSET_DIR = pathlib.Path(__file__).parent / "skill_assets" / SKILL_NAME

logger = logging.getLogger(__name__)


def asset_dir() -> pathlib.Path:
    """Where the bundled skill folder lives."""
    return _ASSET_DIR


async def seed_knowledge_skill(skill_service: Any, *, actor: str = "system") -> bool:
    """Import (or refresh) the bundled knowledge skill. Never raises.

    Returns whether the skill is present afterwards. A failure here must not
    stop the daemon: the layer still works through its tools, an agent just has
    to be told about it some other way.
    """
    if not (_ASSET_DIR / "SKILL.md").is_file():  # pragma: no cover - packaging slip
        logger.warning("knowledge.skill_seed.missing_asset", extra={"path": str(_ASSET_DIR)})
        return False
    try:
        await skill_service.import_local(path=str(_ASSET_DIR), actor=actor, overwrite=True)
    except Exception:
        logger.warning("knowledge.skill_seed.import_failed", exc_info=True)
        return False
    return True
