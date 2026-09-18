"""every reference from one resource to another stops naming it and points at its uid

0089 gave each resource a ``uid``. This revision rewrites the three places a
resource refers to ANOTHER resource, all of which spelled out a name:

1. ``resources.scope_json`` — a per-agent reach allow-list. Its entries are
   agent resource NAMES for `skill` and `channel` (migration 0081 put channel
   scopes into that vocabulary) but agent TYPES for `provider` — a third
   spelling of "which agent", which is the clearest possible evidence that the
   name was never carrying identity.
2. ``kind='channel'`` config's ``default_agent`` — stored as an agent KEY
   (``claude_code``), which is a THIRD name for the same thing.
3. ``conversations.channel_name`` — which channel a conversation is bound to,
   stored as the channel's name and renamed here to ``channel_uid``.

That there were two different spellings for "which agent" is the defect, not an
incidental detail: ``application/channel/agent_vocabulary.py`` existed only to
translate between them, and the bug that module was written to fix was a user
narrowing a channel's reach to the only value the picker offered and being
refused. Both become the uid here, and that module is deleted with this change.

## Why this migration refuses to widen, at length

A reach allow-list is a RESTRICTION. The rule for rewriting one is that every
outcome must be the same restriction or a narrower one, never a broader one,
because the broader direction is invisible: nothing errors, a resource is
simply live somewhere the user had said it should not be.

There are exactly three ways an entry can fail to map, and each is handled
explicitly rather than by a default:

- **A name that matches no registered agent.** Dropped from the list. This is
  not a loss: an unknown name matched nothing before (``domain/scope``'s "unknown
  names are legal and simply never match"), and an absent uid matches nothing
  now. Identical behaviour, one fewer dead entry.
- **Every name in the list fails to map.** The list becomes ``[]`` — dormant —
  and emphatically **not** ``NULL``. ``NULL`` means *unscoped*, i.e. active for
  every agent, so collapsing an all-unresolvable list to ``NULL`` would turn
  "only these agents" into "all agents" on a row the user had deliberately
  narrowed. This is the exact trap the reach work has hit before and it is why
  the rewrite is written as a mapping over entries, never as "replace the
  column when you can".
- **``scope_json`` is already ``NULL``.** Untouched. It was unscoped before and
  stays unscoped; there is nothing to narrow.

``conversations.channel_uid`` is a binding too, but unlike ``default_agent`` a
value that cannot be resolved is set to **NULL** rather than kept. The
difference is what the absent state means for each: a channel with no default
agent is broken and must say so, while a conversation with no channel is an
ordinary terminal conversation — the narrow, correct reading of "the channel
this was bound to is gone". Keeping the dead name would leave the column
holding something no code can interpret.

``default_agent`` is not an allow-list and gets the opposite treatment. It is a
binding — "drive this agent" — so an unmappable value must not be quietly
cleared either: a cleared binding is a channel that silently stops answering.
Where the key maps to no registered agent the value is **left exactly as it
is**, which fails loudly and visibly at the kind's own validation the next time
the channel is touched, with the original value still on screen to fix.

An agent key may match SEVERAL agent rows — two Claude Code installs with
different config directories. The runtime resolved that by taking the first in
registry order (``ResourceRepo.list`` orders by ``kind, name``, and
``agent_keys()`` reads that order), so this picks the same one: the
alphabetically first agent of that type. That is not an improvement invented
here, it is the behaviour being preserved.

Idempotent: an entry that is already a uid maps to itself (the uid lookup
succeeds), and a ``default_agent`` that is already a uid is left alone by the
same test. A second run is a no-op.

Revision ID: 0090
Revises: 0089
Create Date: 2026-09-18
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0096"
down_revision: str | None = "0095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_AGENT_TYPE_KEY = "type"


def _agent_maps(
    bind: sa.engine.Connection,
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]], set[str]]:
    """``(uid_by_name, first_uid_by_key, all_uids_by_key, every_uid)``.

    Two different answers for an agent TYPE, because the two readers of a type
    want different things and conflating them is a real behaviour change:

    - ``first_uid_by_key`` — for ``default_agent``, a binding to ONE agent. The
      runtime resolved a type by taking the first in registry order, so this
      picks the same one.
    - ``all_uids_by_key`` — for a `provider` scope, which is an ALLOW-LIST. A
      connection scoped to ``claude_code`` projected into *every* Claude Code
      agent; collapsing that to the first would silently stop projecting into a
      second install, which is a narrowing nobody asked for and nothing reports.
    """
    rows = bind.execute(
        sa.text(
            "SELECT uid, name, config_json FROM resources WHERE kind = 'agent' ORDER BY kind, name"
        )
    ).fetchall()
    by_name: dict[str, str] = {}
    by_key: dict[str, str] = {}
    all_by_key: dict[str, list[str]] = {}
    for row in rows:
        by_name[row.name] = row.uid
        try:
            config = json.loads(row.config_json)
        except (TypeError, ValueError):
            config = {}
        agent_key = config.get(_AGENT_TYPE_KEY) if isinstance(config, dict) else None
        if isinstance(agent_key, str) and agent_key:
            by_key.setdefault(agent_key, row.uid)
            all_by_key.setdefault(agent_key, []).append(row.uid)
    return by_name, by_key, all_by_key, set(by_name.values())


def _rewrite_scopes(
    bind: sa.engine.Connection,
    by_name: dict[str, str],
    all_by_key: dict[str, list[str]],
    uids: set[str],
) -> None:
    rows = bind.execute(
        sa.text("SELECT id, scope_json FROM resources WHERE scope_json IS NOT NULL")
    ).fetchall()
    rewritten = dropped = 0
    for row in rows:
        try:
            scope = json.loads(row.scope_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(scope, dict):
            continue
        agents = scope.get("agents")
        if not isinstance(agents, list):
            # ``{"agents": null}`` is unrestricted and there is nothing in it to
            # map. Left as it is rather than normalised, because rewriting an
            # unrestricted scope could only ever make it less so by accident.
            continue
        mapped: list[str] = []
        for entry in agents:
            if not isinstance(entry, str):
                continue
            if entry in uids:  # already a uid — this revision has run before
                mapped.append(entry)
            elif entry in by_name:
                # A resource NAME: `skill` and `channel` scopes.
                mapped.append(by_name[entry])
            elif entry in all_by_key:
                # An agent TYPE: `provider` scopes. Expanded to EVERY agent of
                # that type, which is what the entry meant — see _agent_maps.
                mapped.extend(uid for uid in all_by_key[entry] if uid not in mapped)
            else:
                dropped += 1
        if mapped == agents:
            continue
        # NEVER ``None`` here: an empty list is dormant, ``None`` is "every
        # agent". See this module's docstring.
        scope["agents"] = mapped
        bind.execute(
            sa.text("UPDATE resources SET scope_json = :scope WHERE id = :id"),
            {"scope": json.dumps(scope), "id": row.id},
        )
        rewritten += 1
    logger.info("migration.0090.scopes_rewritten; rows=%s dropped_entries=%s", rewritten, dropped)


def _rewrite_default_agents(
    bind: sa.engine.Connection, by_key: dict[str, str], uids: set[str]
) -> None:
    rows = bind.execute(
        sa.text("SELECT id, name, config_json FROM resources WHERE kind = 'channel'")
    ).fetchall()
    rewritten = unmapped = 0
    for row in rows:
        try:
            config = json.loads(row.config_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(config, dict):
            continue
        current = config.get("default_agent")
        if not isinstance(current, str) or not current or current in uids:
            continue
        target = by_key.get(current)
        if target is None:
            # Left verbatim, deliberately. See this module's docstring: a
            # binding that cannot be resolved must fail where the user can see
            # and fix it, not disappear.
            unmapped += 1
            logger.warning(
                "migration.0090.default_agent_unmapped; channel=%s value=%s", row.name, current
            )
            continue
        config["default_agent"] = target
        bind.execute(
            sa.text("UPDATE resources SET config_json = :config WHERE id = :id"),
            {"config": json.dumps(config), "id": row.id},
        )
        rewritten += 1
    logger.info("migration.0090.default_agents_rewritten; rows=%s unmapped=%s", rewritten, unmapped)


def _rewrite_conversation_channels(bind: sa.engine.Connection) -> None:
    """``conversations.channel_name`` -> ``channel_uid``, values remapped.

    The column is renamed in place. SQLite has supported ``RENAME COLUMN``
    since 3.25 and nothing holds a foreign key INTO ``conversations`` on this
    column, so there is no table rebuild to do — which matters, because
    rebuilding a table in SQLite is where an inbound FK quietly loses its
    target.
    """
    inspector = sa.inspect(bind)
    if "conversations" not in set(inspector.get_table_names()):
        return
    columns = {c["name"] for c in inspector.get_columns("conversations")}
    if "channel_uid" not in columns:
        if "channel_name" not in columns:
            return
        op.alter_column("conversations", "channel_name", new_column_name="channel_uid")

    rows = bind.execute(
        sa.text("SELECT id, channel_uid FROM conversations WHERE channel_uid IS NOT NULL")
    ).fetchall()
    remapped = orphaned = 0
    for row in rows:
        target = bind.execute(
            sa.text("SELECT uid FROM resources WHERE kind = 'channel' AND uid = :value"),
            {"value": row.channel_uid},
        ).scalar_one_or_none()
        if target is not None:  # already a uid — this revision has run before
            continue
        target = bind.execute(
            sa.text("SELECT uid FROM resources WHERE kind = 'channel' AND name = :value"),
            {"value": row.channel_uid},
        ).scalar_one_or_none()
        bind.execute(
            sa.text("UPDATE conversations SET channel_uid = :uid WHERE id = :id"),
            {"uid": target, "id": row.id},
        )
        if target is None:
            orphaned += 1
        else:
            remapped += 1
    logger.info("migration.0090.conversation_channels; remapped=%s orphaned=%s", remapped, orphaned)


def upgrade() -> None:
    bind = op.get_bind()
    if "resources" not in set(sa.inspect(bind).get_table_names()):
        return
    by_name, by_key, all_by_key, uids = _agent_maps(bind)
    _rewrite_scopes(bind, by_name, all_by_key, uids)
    _rewrite_default_agents(bind, by_key, uids)
    _rewrite_conversation_channels(bind)


def downgrade() -> None:
    """Put the COLUMN back; leave the VALUES where they are.

    The two halves of this revision reverse differently, and conflating them is
    what a first attempt got wrong.

    **The DDL half must reverse.** ``conversations.channel_name`` was renamed,
    and the revision that created that column drops it by name on the way down
    — so a downgrade that skipped the rename left an earlier revision reaching
    for a column that no longer exists, and the whole chain failed there rather
    than here. Reversible schema is not optional just because the data is not.

    **The DATA half cannot, and must not be guessed.** Going back means turning
    a uid into "the name that resource had", which is only knowable while it
    still exists under a name — and the point of this revision is that the name
    may have changed since. A downgrade that guessed would write a restriction,
    or a channel binding, that the user never set.

    So the values stay as uids. Code below this revision reads a uid where it
    expected a name, matches nothing, and treats those resources as dormant and
    those conversations as unbound — narrow, visible, and recoverable by
    setting the reach again. Stepping forward re-derives the scopes from
    ``_rewrite_scopes``' already-a-uid branch, which is why that branch exists.
    """
    inspector = sa.inspect(op.get_bind())
    if "conversations" not in set(inspector.get_table_names()):
        return
    if "channel_uid" in {c["name"] for c in inspector.get_columns("conversations")}:
        op.alter_column("conversations", "channel_uid", new_column_name="channel_name")
