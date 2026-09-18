"""a channel's and an mcp_server's credential refs stop spelling the resource's name

Two kinds minted the address of a secret out of the resource's NAME:
``channel/<name>/<secret>`` and ``<name>.<env key>``. `provider` already does
not — ``application/provider/service.py::_mint_ref`` returns
``provider/<uuid4 hex>/key`` and says why: deriving a ref from the connection's
name "made the name a key — renaming then had to move the secret". These two
never got the same treatment because neither could be renamed at all, so the
hazard was unreachable. [Resource Identity Is an Immutable
`uid`](../../../../../../docs/decisions/resource-identity-is-an-immutable-uid.md)
makes rename a field on ``PATCH /api/v1/resources/{uid}`` for every kind, which
is what reaches it — so this revision moves the existing refs out of the way of
the rename that now exists.

What a stale ref costs is not cosmetic. ``ResourceService.delete`` releases a
credential by CITATION — it deletes a ref no remaining resource's config names.
That is the right rule, and it is exactly why the store must never hold two
addresses for one secret or one address two resources disagree about: a config
rewritten without its credential row, or a row moved without its config, leaves
a resource citing nothing and a secret nobody claims, and the next delete of an
unrelated row is what makes it visible.

## Why the new ref is DERIVED and not random

``uuid4`` would be wrong here for the same reason it was wrong in 0089. The
synced bundle stores each secret's ciphertext at ``credentials/<ref>.enc``, and
a vault converges through a git remote with no online handshake. Two machines
that never talk must therefore compute the SAME new ref for the same old one,
or the next converge round sees one machine delete ``credentials/a.enc`` and
another add ``credentials/b.enc`` — two edits nothing can pair, over a file
whose contents neither side can read to compare.

So the new ref is a pure function of the old one:

    <kind>/<uuid5(NAMESPACE, old_ref).hex>/<logical key>

and the logical key is taken from the old ref too — its last segment, splitting
on ``/`` and then ``.``, which is ``bot-token`` out of ``channel/tg/bot-token``
and ``SMART_PAT`` out of ``smart.SMART_PAT``. For the refs this revision
actually moves that is the same string as the citing key, by construction; it
is computed from the ref anyway, because a ref cited twice must derive one tail
whichever citation happens to be read first.

The trailing key is kept at all because it is what makes a ref readable in
``coffer credentials list``, and it is not derived from anything mutable — it
came from the secret's own role, not from the resource's label. Random refs are
minted for everything created AFTER this revision, in the frontend
(``lib/credentialRef.ts``); this derivation is used here and nowhere else.

## What this moves, and what it deliberately does not

A ref is moved only when it can be RECONSTRUCTED, whole, from the resource's
name and the key citing it — ``channel/<name>/<secret>`` or ``<name>.<env
key>``, the two strings the two front-end files built. Everything else is left
alone, and that exclusion is the point rather than a gap: a ref the user chose
(what they typed into the MCP edit dialog, or the editable
``mcp/<agent>/<entry>/<KEY>`` default the adopt dialog prefills) is not
name-derived in the sense that hurts. Nothing resolves a secret by matching a
ref against a name — resolution is by exact string, ownership is by citation —
so moving a user's ref would buy nothing and cost them the label they read it
by. Reconstructing against the CURRENT name is sound because neither kind could
be renamed before this change: the name a legacy ref was minted from is still
on the row, and it is a name both machines hold, since it travels in the synced
document.

## The cases, each handled rather than defaulted

- **A config cites a ref with no row in ``credentials``.** Left exactly as it
  is — ref and config both. There is nothing to move, and moving the citation
  alone would be strictly destructive: an unstored ref is usually one still
  sitting in the OS keychain, which ``application/credential_migration.py``
  drains lazily at daemon startup by looking the CITED ref up in the keychain.
  Rewrite the citation and that lookup asks for an address the keychain has
  never heard of, turning "not migrated yet" into "gone". The cost of leaving
  it is that such a resource keeps a name-derived ref until the user re-enters
  the secret, at which point the UI mints an opaque one — a stale label, not a
  lost secret, because ownership is decided by citation and not by the ref
  matching the name.
- **A ``credentials`` row nothing cites.** Untouched. This revision never
  enumerates the table; it walks citations and moves what they point at. An
  uncited row is already what ``release_orphaned_credentials`` is for, and
  renaming it would only produce an orphan under a different name.
- **A ref that is already opaque.** Skipped by the shape test, which is what
  makes a second run a no-op: after one upgrade every rewritten ref matches
  ``<kind>/<32 hex>/``, nothing is planned, nothing is written. (Refs the first
  case left behind are re-examined on every run, and skipped again for the same
  reason — until their secret lands in the store, when they finally move.)
- **A ref the user chose.** Untouched, per the section above.
- **A ref one resource minted and ANOTHER also cites** — possible only by hand,
  since a legacy ref reconstructs against exactly one name. The move is planned
  once, off the resource that minted it, and then EVERY citation of it is
  repointed, in both kinds. Rewriting only the minting resource's half would
  leave the other citing an address the store no longer has.
- **``config_json`` that will not parse.** Skipped whole, with a warning naming
  the resource. A config this cannot read is one it cannot rewrite either half
  of correctly, and half a rewrite is the failure this revision exists to
  prevent.

Revision ID: 0093
Revises: 0092
Create Date: 2026-09-18
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0099"
down_revision: str | None = "0098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

#: The namespace this one-time rewrite derives from. Fixed forever, for the
#: reason 0089's namespace is: change it and two machines upgrading on either
#: side of the change compute different addresses for the same secret, and the
#: ciphertext blob in the bundle is the one file neither of them can open to
#: notice. Written as a literal so no library's hashing convention can move it.
NAMESPACE = uuid.UUID("e1917b6e-1ceb-42cf-9a60-d89ec9321ef7")

#: Kinds whose refs this revision moves. `provider` is absent on purpose: it
#: already mints opaque refs, and the legacy ``provider/<name>/key`` values its
#: service documents as "just strings this config happens to hold" are left to
#: the decision that was already taken about them.
KINDS = ("channel", "mcp_server")

#: A channel spells each secret in its own top-level field (the same tuple
#: ``application/channel/kind.py`` extracts from), and the front end minted the
#: ref from the field's own name: ``bot_token_ref`` -> ``bot-token``.
CHANNEL_REF_FIELDS = ("bot_token_ref", "app_secret_ref", "signing_secret_ref", "tunnel_token_ref")

#: Already migrated — or minted after this revision, which looks the same.
OPAQUE = re.compile(r"^(?:channel|mcp_server)/[0-9a-f]{32}/")


def logical_key(old_ref: str) -> str:
    """The readable tail of a ref, out of the ref alone.

    Both legacy shapes put the secret's role last, separated by ``/`` in a
    channel ref and by ``.`` in an mcp_server one, so one rule reads both. For
    a ref this revision actually moves it is the citing key by construction —
    ``_was_minted_from_the_name`` only admits refs that spell it — but it is
    computed from the REF, not from the citation, because a ref cited twice
    must derive one tail whichever citation is read first.
    """
    tail = old_ref.replace("/", ".").split(".")[-1]
    return tail or "key"


def new_ref(kind: str, old_ref: str) -> str:
    """The opaque address ``old_ref`` moves to — the same on every machine."""
    return f"{kind}/{uuid.uuid5(NAMESPACE, old_ref).hex}/{logical_key(old_ref)}"


def _citations(kind: str, config: Any) -> list[tuple[str, str]]:
    """``(citing key, ref)`` for every credential ref ``config`` names.

    The key is the channel's config field or the mcp_server's env-var key — it
    is what the front end built the legacy ref out of, so it is what
    ``_was_minted_from_the_name`` needs to recognise one.
    """
    if not isinstance(config, dict):
        return []
    if kind == "channel":
        return [
            (f, config[f])
            for f in CHANNEL_REF_FIELDS
            if isinstance(config.get(f), str) and config[f]
        ]
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return []
    refs = transport.get("credential_refs")
    if not isinstance(refs, dict):
        return []
    return [(str(k), v) for k, v in refs.items() if isinstance(v, str) and v]


def _was_minted_from_the_name(kind: str, name: str, key: str, ref: str) -> bool:
    """Whether ``ref`` is one the front end built out of ``name``.

    An exact reconstruction, not a prefix or a guess. The two shapes are
    ``channel/<name>/<secret>`` and ``<name>.<env key>``, and matching the whole
    string is what keeps this revision to its own business: a ref the USER
    chose — the ``mcp/<agent>/<entry>/<KEY>`` default the adopt dialog prefills
    and lets them edit, or anything they typed — is not name-derived in the
    sense that matters here and is left exactly as it is. Moving it would buy
    nothing (nothing resolves a secret by matching a ref against a name) and
    would cost the label the user chose to read it by.

    The reconstruction uses the resource's CURRENT name, which is sound only
    because neither of these kinds could be renamed before this revision's
    change: the name a legacy ref was minted from is still the name on the row.
    That also makes the test agree across machines, since the name travels in
    the synced document.
    """
    if kind == "channel":
        secret = key.removesuffix("_ref").replace("_", "-")
        return ref == f"channel/{name}/{secret}"
    return ref == f"{name}.{key}"


def _rewrite_config(kind: str, config: dict[str, Any], plan: dict[str, str]) -> bool:
    """Point every planned citation at its new ref. True if anything changed."""
    changed = False
    if kind == "channel":
        for field in CHANNEL_REF_FIELDS:
            current = config.get(field)
            if isinstance(current, str) and current in plan:
                config[field] = plan[current]
                changed = True
        return changed
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return False
    refs = transport.get("credential_refs")
    if not isinstance(refs, dict):
        return False
    for key, current in list(refs.items()):
        if isinstance(current, str) and current in plan:
            refs[key] = plan[current]
            changed = True
    return changed


def _load(bind: sa.engine.Connection) -> list[tuple[Any, str, dict[str, Any]]]:
    """``(row, kind, parsed config)`` for every channel / mcp_server resource.

    A row whose ``config_json`` will not parse is dropped here with a warning
    and never reaches the plan, so neither half of it is touched.
    """
    placeholders = ", ".join(f"'{k}'" for k in KINDS)
    rows = bind.execute(
        sa.text(f"SELECT id, kind, name, config_json FROM resources WHERE kind IN ({placeholders})")
    ).fetchall()
    out: list[tuple[Any, str, dict[str, Any]]] = []
    for row in rows:
        try:
            config = json.loads(row.config_json)
        except (TypeError, ValueError):
            logger.warning("migration.0093.config_unparseable; kind=%s name=%s", row.kind, row.name)
            continue
        if not isinstance(config, dict):
            logger.warning("migration.0093.config_not_object; kind=%s name=%s", row.kind, row.name)
            continue
        out.append((row, row.kind, config))
    return out


def _plan(
    bind: sa.engine.Connection, loaded: list[tuple[Any, str, dict[str, Any]]]
) -> dict[str, str]:
    """``{old ref: new ref}`` for every name-derived ref that has a stored row.

    Two filters, and they answer different questions. ``OPAQUE`` asks "has this
    already been done"; ``_was_minted_from_the_name`` asks "is this mine to
    move at all". A ref that passes both, and that the store actually holds,
    gets a new address here and its ``credentials`` row moved to it; every
    citation of it — including one from a resource whose own name does not
    spell it — is repointed by ``_rewrite_config`` afterwards, which is what
    keeps a ref pasted into a second config from being left dangling.
    """
    minted: dict[str, str] = {}
    for row, kind, config in loaded:
        for key, ref in _citations(kind, config):
            if OPAQUE.match(ref) or not _was_minted_from_the_name(kind, row.name, key, ref):
                continue
            minted[ref] = kind

    plan: dict[str, str] = {}
    for old, kind in minted.items():
        target = new_ref(kind, old)
        stored = set(
            bind.execute(
                sa.text("SELECT ref FROM credentials WHERE ref IN (:old, :new)"),
                {"old": old, "new": target},
            )
            .scalars()
            .all()
        )
        if old not in stored and target not in stored:
            # Nothing stored under either address: leave the citation alone.
            # See this module's docstring, first case — the secret is most
            # likely still in the OS keychain under the name-derived ref, and
            # rewriting the citation is what would lose it.
            logger.info("migration.0093.ref_not_stored; ref=%s", old)
            continue
        if old in stored and target in stored:
            # Both addresses hold ciphertext — only reachable if a previous run
            # was interrupted between the two writes. The new one is what the
            # citations will point at; the old is left in place rather than
            # deleted, because a secret is not something to throw away on an
            # inference about how it got there.
            logger.warning("migration.0093.both_refs_stored; old=%s new=%s", old, target)
        elif old in stored:
            bind.execute(
                sa.text("UPDATE credentials SET ref = :new WHERE ref = :old"),
                {"new": target, "old": old},
            )
        plan[old] = target
    return plan


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "resources" not in tables or "credentials" not in tables:
        return

    loaded = _load(bind)
    plan = _plan(bind, loaded)
    if not plan:
        logger.info("migration.0093.no_name_derived_refs")
        return

    rewritten = 0
    for row, kind, config in loaded:
        if not _rewrite_config(kind, config, plan):
            continue
        bind.execute(
            sa.text("UPDATE resources SET config_json = :config WHERE id = :id"),
            {"config": json.dumps(config), "id": row.id},
        )
        rewritten += 1
    logger.info("migration.0093.refs_moved; refs=%s resources=%s", len(plan), rewritten)


def downgrade() -> None:
    """A no-op, and it cannot honestly be anything else.

    Going back means turning ``channel/<uuid5>/bot-token`` into
    ``channel/<name>/bot-token``, which needs the name the channel had at the
    moment this revision ran. ``uuid5`` does not invert, and the name is exactly
    what the resource is now free to change — so the only way to reconstruct the
    old ref would be to guess from the CURRENT name, which is wrong precisely in
    the case that matters: a channel renamed since the upgrade would get a ref
    naming a label it never had a secret under, and the secret would be
    unreachable under both spellings.

    Nothing is lost by doing nothing. A ref is an address, and every reader of
    one — the credential store, ``release_orphaned_credentials``, the sync
    bundle's blob path — takes it verbatim from the config that cites it. Code
    below this revision reads an opaque ref and resolves it exactly as it
    resolved a name-derived one; only a ref MINTED below this revision would be
    name-derived again, and that is the state the upgrade path already handles.

    What a downgrade does cost is the fleet: a machine that steps back and
    re-creates a secret mints the old shape, and stepping forward moves it
    again under a different uuid5 input. That is one converge round of churn on
    one blob, which is the honest price of a schema-free data rewrite.
    """
