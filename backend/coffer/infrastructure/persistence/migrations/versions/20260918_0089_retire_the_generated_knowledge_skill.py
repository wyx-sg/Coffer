"""the generated ``coffer-knowledge`` skill is retired: its delivered copies are removed

Coffer's manual and its knowledge catalogue are one skill now, ``coffer-guide``,
and that one is an ordinary ``skill`` resource: a master folder under
``~/.coffer/skills/``, a row, and the same links every other skill is delivered
by. What it replaces was none of those things. ``coffer-knowledge`` was written
directly into each agent's own ``skills/`` directory as real bytes by the
knowledge layer, with no row, no master and no binding — which is exactly why
nothing else can clean it up. Delivery reconciliation only ever reclaims what a
binding says was delivered, and there is no binding here to reclaim from.

Left alone, every agent would keep a folder describing a contract that has
moved: it names ``coffer__write`` correctly but tells the agent that the
catalogue it carries is the whole of what Coffer offers, and it will never be
rewritten again, because the code that used to rewrite it is gone. A stale
manual is worse than none — the agent has no way to tell it is reading last
month's rules.

So this removes the folder from every registered agent's skill directory.

**It only removes what Coffer itself wrote.** The folder is deleted when it is
a symlink (an older shared-master delivery) or when it is a directory holding
the generated pair — ``SKILL.md`` plus the ``README.md`` that delivery stamped
to say the contents were generated. A directory that does not look like that is
a skill somebody else put at that name, and it is left exactly where it is.

Idempotent: a second run finds nothing to remove. It never raises — an
unreadable or unwritable agent directory is logged and skipped, because a
leftover folder is untidy while a migration that cannot finish is a daemon that
cannot start.

Revision ID: 0089
Revises: 0088
Create Date: 2026-09-18
"""

from __future__ import annotations

import json
import logging
import pathlib
import shutil
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089"
down_revision: str | None = "0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

#: The retired skill's folder name, in every agent's own ``skills/``.
_RETIRED = "coffer-knowledge"

#: What the generated delivery always left behind. Both present means Coffer
#: wrote this folder; anything else means somebody did.
_GENERATED_MARKERS = ("SKILL.md", "README.md")


def _is_coffers_own(folder: pathlib.Path) -> bool:
    """Whether this folder is the generated delivery and not someone's skill."""
    return all((folder / name).is_file() for name in _GENERATED_MARKERS)


def _skill_dirs(bind: sa.engine.Connection) -> list[pathlib.Path]:
    """Every registered agent's effective skill directory.

    Read through the agent kind's own config model rather than by joining
    strings here: where an agent's skills live is a question that model already
    answers, including the per-type defaults a raw ``config_dir`` does not.
    """
    from coffer.domain.agent.config import AgentConfig

    rows = bind.execute(
        sa.text("SELECT name, config_json FROM resources WHERE kind = 'agent'")
    ).fetchall()
    dirs: list[pathlib.Path] = []
    for name, config_json in rows:
        try:
            dirs.append(AgentConfig.model_validate(json.loads(config_json)).resolved_skill_dir())
        except Exception:
            logger.warning("0089: could not resolve skill dir for agent %r — skipped", name)
    return dirs


def upgrade() -> None:
    removed = 0
    for skill_dir in _skill_dirs(op.get_bind()):
        folder = skill_dir / _RETIRED
        try:
            if folder.is_symlink():
                folder.unlink()
            elif folder.is_dir() and _is_coffers_own(folder):
                shutil.rmtree(folder, ignore_errors=True)
            else:
                continue
            removed += 1
        except OSError:
            logger.warning("0089: could not remove %s — left in place", folder, exc_info=True)
    if removed:
        logger.info("0089: removed %d delivered copy/copies of %r", removed, _RETIRED)


def downgrade() -> None:
    """Not reversible, and nothing is lost by that.

    The folder was generated output, never a source of truth: the corpus it
    described is untouched under ``~/.coffer/knowledge/``, and a downgrade that
    wanted the old skill back would have to re-render it from code this build
    no longer contains.
    """
