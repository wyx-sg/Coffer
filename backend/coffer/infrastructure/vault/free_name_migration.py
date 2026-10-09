"""ONE-TIME migration: a provider's or a channel's title becomes its name, and
its file is named by its uid (ADR provider-and-channel-names-are-free-text).

A provider and a channel used to carry two labels: a fixed slug ``name`` and an
optional free-text ``title`` the app showed in its place. Now the name is the
free text and there is no title. On each start, before the resource store
first reads, every provider file (in the vault) and every channel file (in
``local/``) that still has the old shape is rewritten:

- a non-blank ``title`` replaces ``name``; a name that would then collide with
  another of the same kind, ignoring case, gets `` (2)``, `` (3)``… appended
  (a name kept as it was wins over a title that would take it);
- the ``title`` key is dropped;
- the file moves to ``<uid>.json``, so a later rename never moves it.

Every step is a pure function of the files, so two machines that migrate the
same vault write the same bytes to the same paths, and their commits merge
cleanly. A file already in the new shape is left alone, so the migration runs
on every start and does nothing once the files are migrated, including those a
machine still on the previous build writes later. Delete this module, its call
in ``vault_composition`` and its test once every machine runs this build.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from coffer.domain.resource import FREE_NAME_MAX_LEN, InvalidResourceNameError, normalise_free_name
from coffer.domain.vault.document import DocumentInvalid, decode, encode
from coffer.domain.vault.layout import DOCUMENT_SUFFIX, RESOURCES
from coffer.domain.vault.writers import OP_RENAME
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.atomic import atomic_write, remove_file
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.instance import vault_writer

log = logging.getLogger(__name__)

PROVIDERS = f"{RESOURCES}/provider"
CHANNELS = f"{RESOURCES}/channel"
SUMMARY = "Named providers by their titles and filed them by uid"

#: ``{old path: (new path, new bytes)}``; the new path equals the old one when
#: only the contents change.
Plan = dict[str, tuple[str, bytes]]


def _wanted_name(doc: dict[str, Any]) -> str:
    title = doc.get("title")
    name = doc.get("name")
    for candidate in (title, name):
        if isinstance(candidate, str) and candidate.strip():
            try:
                return normalise_free_name(candidate)
            except InvalidResourceNameError:
                continue
    return name if isinstance(name, str) else ""


def _unique(name: str, taken: set[str]) -> str:
    """``name``, or ``name (n)`` for the first free ``n``, within the cap."""
    if name.casefold() not in taken:
        return name
    n = 2
    while True:
        suffix = f" ({n})"
        candidate = name[: FREE_NAME_MAX_LEN - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
        n += 1


def plan(files: dict[str, bytes], directory: str) -> Plan:
    """What to rewrite among ``files`` (``{path: bytes}`` under
    ``directory``). Pure: the same files always give the same plan."""
    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(files):
        try:
            doc = decode(files[path])
        except DocumentInvalid:
            continue
        if isinstance(doc.get("uid"), str) and isinstance(doc.get("name"), str):
            docs[path] = doc
    # Names nothing asks to change are held first, so a title never takes a
    # name a resource already has; a name that only differed by case from
    # another (unique before, not now) is the one that moves aside.
    order = sorted(docs, key=lambda p: ("title" in docs[p], p))
    taken: set[str] = set()
    out: Plan = {}
    for path in order:
        doc = docs[path]
        new = {k: v for k, v in doc.items() if k != "title"}
        new["name"] = _unique(_wanted_name(doc), taken)
        taken.add(new["name"].casefold())
        target = f"{directory}/{doc['uid']}{DOCUMENT_SUFFIX}"
        if new != doc or path != target:
            out[path] = (target, encode(new))
    # A target another file holds, or two files would move to (a hand copy
    # that kept the uid), is left for the validator to report; both stay.
    held = set(files) - set(out)
    targets = [new for new, _ in out.values()]
    return {
        old: (new, data)
        for old, (new, data) in out.items()
        if new == old or (new not in held and targets.count(new) == 1)
    }


def _migrate_vault(home: Path | None) -> int:
    writer = vault_writer(vault_root(home))
    repo = writer.repo
    tree = {p: b for p, b in repo.tree("HEAD", PROVIDERS).items() if p.endswith(DOCUMENT_SUFFIX)}
    blobs = repo.read_blobs(sorted(set(tree.values())))
    work = plan({p: blobs.get(b, b"") for p, b in tree.items()}, PROVIDERS)
    if not work:
        return 0
    with writer.begin(commit_meta(OP_RENAME, SUMMARY, "system")) as txn:
        for old, (new, data) in sorted(work.items()):
            if new == old:
                txn.write(old, data, Expect.HEAD)
            else:
                txn.write(new, data, Expect.ABSENT)
                txn.delete(old, Expect.HEAD)
    return len(work)


def _migrate_local(home: Path | None) -> int:
    root = local_root(home)
    files: dict[str, bytes] = {}
    for file in sorted((root / CHANNELS).glob(f"*{DOCUMENT_SUFFIX}")):
        try:
            files[f"{CHANNELS}/{file.name}"] = file.read_bytes()
        except OSError:
            continue
    work = plan(files, CHANNELS)
    for old, (new, data) in sorted(work.items()):
        atomic_write(root / new, data)
        if new != old:
            remove_file(root / old, stop_at=root)
    return len(work)


def name_by_title(home: Path | None = None) -> int:
    """Run the migration (blocking); the number of files rewritten. The vault
    side and the local side fail apart: one that cannot be written now (an
    unsettled hand edit) is logged and tried again next start."""
    changed = 0
    for side, run in (("vault", _migrate_vault), ("local", _migrate_local)):
        try:
            changed += run(home)
        except Exception:
            log.warning("resource.free_name_migration_failed", extra={"side": side}, exc_info=True)
    if changed:
        log.info("resource.free_name_migration.done files=%d", changed)
    return changed


__all__ = ["SUMMARY", "name_by_title", "plan"]
