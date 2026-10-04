"""What a rehearsal checks: everything the old home held is in the new one,
and a rollback gives the old home back byte for byte.

An :class:`Inventory` is taken of the home before the upgrade — every
resource with its config, every secret ref, the bytes of every file in every
tree that moves, the history rows — and :func:`check` compares the upgraded
home with it. A knowledge document that carried a curation stamp is compared
without it, since stripping it is part of the upgrade.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coffer.domain.vault.document import DocumentInvalid, parse_resource
from coffer.domain.vault.portability import expand_home
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import decode, render
from coffer.infrastructure.secret.encrypted_store import ref_files
from coffer.infrastructure.vault.home import coffer_home
from coffer.infrastructure.vault.migration.connection_choice import settle_connection_choice
from coffer.infrastructure.vault.migration.knowledge import CURATED_AT_KEY
from coffer.infrastructure.vault.migration.legacy_db import read_legacy
from coffer.infrastructure.vault.migration.places import (
    LEGACY_DB,
    PRE_LAYOUT_REVISION,
    RUNS_DB,
    SIDE_FILES,
    TREE_MOVES,
    at,
)
from coffer.infrastructure.vault.reach_store import ReachStore, reach_path

if TYPE_CHECKING:
    from coffer.infrastructure.vault.migration.run import UpgradeDb

#: The history tables whose rows must all reach ``runs.db``.
HISTORY_TABLES = ("audit_log", "conversations", "chat_messages", "mcp_invocations")

#: Names a rollback leaves beside the restored home (its own backup set and
#: what it set aside); everything else must be as it was.
ROLLBACK_ARTIFACTS = ("pre-vault", "coffer.db.pre-vault", "MIGRATION_ROLLED_BACK")


def is_artifact(rel: str) -> bool:
    head = rel.split("/", 1)[0]
    return ".rolled-back-" in head or any(
        head == a or head.startswith(a + "-") for a in ROLLBACK_ARTIFACTS
    )


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_tree(root: Path) -> dict[str, str]:
    """``{relative path: sha256}`` of every file under ``root`` (a link: its target)."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in [*filenames, *(d for d in dirnames if (base / d).is_symlink())]:
            path = base / name
            rel = path.relative_to(root).as_posix()
            out[rel] = (
                f"link:{os.readlink(path)}" if path.is_symlink() else _digest(path.read_bytes())
            )
    return out


def _normal(rel: str, data: bytes) -> str:
    """A knowledge document's bytes as the upgrade leaves them (stamp stripped)."""
    if rel.startswith("vault/knowledge/") and rel.endswith(".md"):
        fm, body = split_frontmatter(decode(data))
        if CURATED_AT_KEY in fm:
            fm.pop(CURATED_AT_KEY)
            return _digest(render(fm, body).encode("utf-8"))
    return _digest(data)


def _target(rel: str) -> str | None:
    for source, target in TREE_MOVES:
        if rel == source or rel.startswith(source + "/"):
            return target + rel[len(source) :]
    return None


@dataclass
class Inventory:
    resources: dict[str, tuple[str, str, dict[str, Any]]] = field(default_factory=dict)
    secrets: set[str] = field(default_factory=set)
    #: ``{path the file has after the upgrade: digest}``.
    files: dict[str, str] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)


def _count(db: Path, tables: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    with contextlib.closing(sqlite3.connect(db)) as conn:
        present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            if table in present:
                out[table] = int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    return out


def take_inventory(home: Path, *, upgrade_db: UpgradeDb | None = None) -> Inventory:
    """What ``home`` holds before its upgrade. The database is read from a
    scratch copy, so taking the inventory changes nothing in the home.

    The upgrade reads the database at ``PRE_LAYOUT_REVISION``, after the
    database's own migrations have rewritten what they rewrite (a secret
    reference is renamed, a retired field is dropped) and before the layout
    move. With ``upgrade_db`` the scratch copy is brought to that revision
    first, so the inventory states what the upgrade will carry, not what an
    older revision happened to hold. The connection choice then moves onto the
    agents exactly as the upgrade moves it."""
    inv = Inventory()
    legacy = at(home, LEGACY_DB)
    if legacy.is_file():
        with tempfile.TemporaryDirectory(prefix="coffer-inventory-") as scratch:
            copy = Path(scratch) / LEGACY_DB
            for side in ("", *SIDE_FILES):
                source = legacy.with_name(legacy.name + side)
                if source.is_file():
                    shutil.copy2(source, copy.with_name(copy.name + side))
            if upgrade_db is not None:
                from coffer.infrastructure.vault.migration.run import sqlite_url

                upgrade_db(sqlite_url(copy), PRE_LAYOUT_REVISION)
            state = read_legacy(copy)
            resources = settle_connection_choice(state.resources)
            inv.resources = {r.uid: (r.kind, r.name, r.config) for r in resources}
            inv.secrets = {str(c["ref"]) for c in state.secrets}
            inv.rows = _count(copy, HISTORY_TABLES)
    base = coffer_home(home)
    for rel, digest in hash_tree(base).items():
        if "/.git/" in f"/{rel}" or rel.startswith("knowledge/.git"):
            continue
        target = _target(rel)
        if target is None:
            continue
        data = (base / rel).read_bytes() if not (base / rel).is_symlink() else b""
        inv.files[target] = _normal(target, data) if data else digest
    return inv


def _resource_files(home: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for cls in ("vault", "local", "derived"):
        for path in sorted(at(home, cls).glob("resources/*/*.json")):
            try:
                doc = parse_resource(path.read_bytes())
            except DocumentInvalid:
                continue
            if doc.uid:
                out[doc.uid] = {"kind": doc.kind, "name": doc.name, "config": doc.config}
    return out


def check(home: Path, inv: Inventory) -> list[str]:
    """Every way the upgraded ``home`` falls short of ``inv``; empty when none."""
    problems: list[str] = []
    found = _resource_files(home)
    reach = ReachStore(reach_path(home)).all()
    for uid, (kind, name, config) in sorted(inv.resources.items()):
        doc = found.get(uid)
        if doc is None:
            problems.append(f"resource {kind} {name} ({uid}) has no file")
            continue
        if (doc["kind"], doc["name"]) != (kind, name):
            problems.append(f"resource {uid} is {doc['kind']} {doc['name']}, was {kind} {name}")
        if expand_home(doc["config"], str(home)) != config:
            problems.append(f"resource {kind} {name}: config differs")
        if uid not in reach:
            problems.append(f"resource {kind} {name}: no reach record")
    stored = set(ref_files(home))
    problems += [f"secret {ref} has no ciphertext file" for ref in sorted(inv.secrets - stored)]
    base = coffer_home(home)
    for rel, digest in sorted(inv.files.items()):
        path = base / rel
        if not path.exists() and not path.is_symlink():
            problems.append(f"{rel} is missing")
        elif not path.is_symlink() and _normal(rel, path.read_bytes()) != digest:
            problems.append(f"{rel} changed")
    runs = at(home, RUNS_DB)
    if inv.rows and runs.is_file():
        after = _count(runs, HISTORY_TABLES)
        for table, n in inv.rows.items():
            if after.get(table) != n:
                problems.append(f"{table}: {n} rows before, {after.get(table)} after")
    return problems


def restored(before: dict[str, str], home: Path) -> list[str]:
    """How the rolled-back home differs from ``before`` (its rollback's own
    artifacts aside)."""
    after = {k: v for k, v in hash_tree(coffer_home(home)).items() if not is_artifact(k)}
    wanted = {k: v for k, v in before.items() if not is_artifact(k)}
    out = [f"{k} is missing after the rollback" for k in sorted(wanted.keys() - after.keys())]
    out += [f"{k} is new after the rollback" for k in sorted(after.keys() - wanted.keys())]
    out += [
        f"{k} differs after the rollback"
        for k in sorted(wanted)
        if k in after and after[k] != wanted[k]
    ]
    return out


__all__ = ["Inventory", "check", "hash_tree", "is_artifact", "restored", "take_inventory"]
