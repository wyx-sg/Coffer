"""a skill's config stops carrying a second copy of the skill's name

``kind='skill'`` ``config_json`` held ``skill_md_name``: the ``name`` read out
of the folder's ``SKILL.md`` frontmatter at import time. The same read also
decides the resource's own ``name`` — ``application/skill/lifecycle_ops`` does
``name = validation.frontmatter.name`` and then passes that identical string as
``skill_md_name`` — so the column and the config key were never two facts. They
were one fact written twice.

Nothing ever read the second copy. Not the HTTP schemas, not the frontend, not
the CLI, not the sync serializer, not the skill service itself: a repo-wide
search for the key finds the line that writes it, the model that declares it,
and test fixtures. It was write-only for its whole life.

## Why a field nobody reads still had to go

Because "nobody reads it" stopped being the end of the story when renaming
arrived. Before [Resource Identity Is an Immutable
`uid`](../../../../../../docs/decisions/resource-identity-is-an-immutable-uid.md)
a skill could not be renamed at all, so the two copies could not drift and the
duplication was merely untidy. Renaming is a ``PATCH`` field for every kind
now, and the skill kind's ``on_rename`` hook has to carry the name onto disk —
into the master folder's name, into each delivered symlink, and into the
frontmatter the agent product actually reads.

Had ``skill_md_name`` stayed, that hook would have had a fourth copy to update,
and every future writer would have had to remember it. This codebase has paid
for "one field answering two questions" before; the fix is to have one place
the name lives, and it is ``resources.name``.

## Why this migration is not optional

``SkillConfig`` is ``extra="forbid"``. The moment the code drops the field, a
row whose stored ``config_json`` still carries it fails validation — and that
validation runs on every read path that parses a skill's config, so the skill
becomes unloadable rather than merely stale. Code and data have to move in the
same change. (Migrations 0029 and 0032 stripped retired skill config keys for
exactly this reason; this is the same shape.)

Idempotent: the key is popped when present and the row is only rewritten when
something actually changed, so a second run touches nothing.

Revision ID: 0092
Revises: 0091
Create Date: 2026-09-18
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0092"
down_revision: str | None = "0091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_KEY = "skill_md_name"


def _skill_rows(bind: sa.engine.Connection) -> list[sa.Row[tuple[int, str, str]]]:
    if "resources" not in set(sa.inspect(bind).get_table_names()):
        return []
    return list(
        bind.execute(
            sa.text("SELECT id, name, config_json FROM resources WHERE kind = 'skill'")
        ).fetchall()
    )


def _config_of(row: sa.Row[tuple[int, str, str]]) -> dict[str, object] | None:
    """The row's parsed config, or ``None`` when it is not a JSON object.

    A row whose ``config_json`` will not parse is left alone rather than
    repaired or deleted. It is already broken in a way this revision did not
    cause and cannot diagnose, and rewriting it would destroy whatever a person
    might still recover from it by hand.
    """
    try:
        config = json.loads(row.config_json)
    except (TypeError, ValueError):
        logger.warning("migration.0092.unparseable_config; skill=%s", row.name)
        return None
    return config if isinstance(config, dict) else None


def upgrade() -> None:
    bind = op.get_bind()
    stripped = divergent = 0
    for row in _skill_rows(bind):
        config = _config_of(row)
        if config is None or _KEY not in config:
            continue
        stored = config.pop(_KEY)
        if stored != row.name:
            # Not expected and not a reason to stop. Every shipped write path
            # set the two from the same string, and renaming a skill was
            # impossible until the change this revision belongs to — so a
            # disagreement here can only come from a hand-edited database.
            #
            # ``resources.name`` wins, because it is the one the rest of the
            # system has always used: it is the master folder's name under
            # ~/.coffer/skills/, the name of every delivered copy in an agent's
            # skills directory, and the (kind, name) uniqueness constraint's
            # half. The discarded value is logged so it is not lost silently.
            divergent += 1
            logger.warning(
                "migration.0092.name_disagreed; skill=%s discarded=%r",
                row.name,
                stored,
            )
        bind.execute(
            sa.text("UPDATE resources SET config_json = :config WHERE id = :id"),
            {"config": json.dumps(config), "id": row.id},
        )
        stripped += 1
    logger.info("migration.0092.stripped; rows=%s divergent=%s", stripped, divergent)


def downgrade() -> None:
    """Puts the key back, and — unusually for this series — loses nothing.

    The sibling data migrations in this change are one-way because they turn a
    name into a uid, and the name a resource had is not recoverable afterwards.
    This one is the opposite case. ``skill_md_name`` was defined as a copy of
    the skill's own name, every write path set the two from the same string,
    and the code below this revision keeps them equal. So the pre-0092 value is
    not being guessed at here — it is being recomputed from the field it was
    always a copy of.

    It also has to be restored rather than merely tolerated: below this
    revision ``SkillConfig`` declares ``skill_md_name`` as a REQUIRED field
    under ``extra="forbid"``, so a downgraded database missing it would fail
    validation on every skill, exactly as an un-upgraded one would fail with it
    present. The break is symmetric, so the repair must be too.

    The one thing that does not come back is a hand-edited value that had
    diverged from ``resources.name``; ``upgrade`` logs those as it discards
    them, and there is nowhere left to read them from.
    """
    bind = op.get_bind()
    restored = 0
    for row in _skill_rows(bind):
        config = _config_of(row)
        if config is None or config.get(_KEY) == row.name:
            continue
        config[_KEY] = row.name
        bind.execute(
            sa.text("UPDATE resources SET config_json = :config WHERE id = :id"),
            {"config": json.dumps(config), "id": row.id},
        )
        restored += 1
    logger.info("migration.0092.restored; rows=%s", restored)
