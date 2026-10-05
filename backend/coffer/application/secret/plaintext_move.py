"""Move plaintext secrets found in managed resources into the store.

Spec secret "Move plaintext secrets in managed resources into the store".
This module owns the move's *order*, not the detection or the file I/O
(``coffer.infrastructure.secret.plaintext_findings`` supplies those):

* **store first** — a value is written to the store and read back before
  anything that held it is changed, so a failure leaves the original in place;
* **a skill's value** becomes a standalone ``secret/<uuid4 hex>`` (Coffer mints
  the id; the proposed name is its label) and its file is
  rewritten to cite it; a file that cannot be rewritten keeps its values and
  its findings come back skipped as ``stored``;
* **a server's value** becomes a ref of the server's own and the server's
  config is changed through the resource service (``update_config``), so the
  change is validated, audited and reconciled like any edit. If that fails,
  the refs just written are deleted again: nothing is left half-moved.

A finding names where a value is and never the value; the value only lives
in a :class:`Hit`, which does not print it.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

from coffer.domain.auth_scheme import split_scheme
from coffer.domain.secrets import SecretNote, mint_secret_name, secret_ref


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    """One plaintext value that could move into the store (no value inside)."""

    id: str
    source: str  # "skill" | "mcp_server"
    #: The skill's or the server's name.
    resource: str
    resource_uid: str | None
    #: A skill's file, and the line in it.
    path: str | None
    line: int | None
    #: A server's ``"env"`` or ``"header"``.
    field: str | None
    key: str
    #: A skill's secret's label; its id and a server's ref are minted on import.
    proposed_name: str | None
    #: The id of the detector rule that found the value.
    rule: str


@dataclasses.dataclass(frozen=True, slots=True)
class Hit:
    finding: Finding
    value: str = dataclasses.field(repr=False)
    #: Where the value sits in its file's text, as offsets (skills only): a
    #: value that spans lines (a PEM private key) is replaced whole.
    start: int = -1
    end: int = -1
    #: The server's config as it was read (servers only).
    config: dict[str, Any] | None = dataclasses.field(default=None, repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class ScanResult:
    findings: list[Finding]
    #: How many files and servers were read, so "nothing found" can say how
    #: much was looked at.
    files_checked: int = 0
    servers_checked: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class Moved:
    id: str
    source: str
    resource: str
    #: A skill's minted standalone name (``None`` in a dry run).
    name: str | None
    #: The ref the value is stored under (``None`` in a server's dry run: it
    #: is minted on import).
    ref: str | None
    #: The label a skill's secret gets (the name the finding proposed).
    label: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Skipped:
    id: str
    source: str
    resource: str
    reason: str
    #: The secret the value was stored as, when it was stored.
    name: str | None = None
    #: The value is in the store but the file still holds it.
    stored: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    moved: list[Moved]
    skipped: list[Skipped]
    dry_run: bool
    #: One audit ``details`` per value stored (never a value).
    stored: list[dict[str, str]]


class SecretStore(Protocol):
    def set(self, ref: str, value: str) -> None: ...
    def peek(self, ref: str) -> str | None: ...
    def delete(self, ref: str) -> None: ...


#: ``(uid, new config)`` — ``ResourceService.update_config`` with the actor bound.
UpdateConfig = Callable[[str, dict[str, Any]], Awaitable[object]]
#: ``(path, hits, names)`` — replace each hit's value with its reference.
RewriteFile = Callable[[str, list[Hit], dict[str, str]], None]


def _put_standalone(store: SecretStore, name: str, value: str) -> bool:
    """Store ``secret/<name>``; true once it reads back as ``value``."""
    ref = secret_ref(name)
    store.set(ref, value)
    if store.peek(ref) == value:
        return True
    store.delete(ref)
    return False


#: ``(ref, note)`` — keep the notes of a minted secret: the label a person will
#: see, or the resource it was minted for.
SetNote = Callable[[str, SecretNote], None]


def _move_skills(
    hits: list[Hit],
    store: SecretStore,
    rewrite: RewriteFile,
    dry_run: bool,
    set_note: SetNote,
) -> tuple[list[Moved], list[Skipped], list[dict[str, str]]]:
    moved: list[Moved] = []
    skipped: list[Skipped] = []
    stored: list[dict[str, str]] = []
    by_file: dict[str, list[Hit]] = {}
    names: dict[str, str] = {}
    for h in hits:
        f = h.finding
        label = f.proposed_name or "imported"
        if dry_run:
            moved.append(Moved(f.id, f.source, f.resource, None, None, label))
            continue
        name = mint_secret_name()
        if not _put_standalone(store, name, h.value):
            skipped.append(
                Skipped(f.id, f.source, f.resource, "the store did not read the value back")
            )
            continue
        set_note(secret_ref(name), SecretNote(label=label))
        names[f.id] = name
        by_file.setdefault(f.path or "", []).append(h)
        moved.append(Moved(f.id, f.source, f.resource, name, secret_ref(name), label))
        stored.append(_audit(f, name=name))
    for path, file_hits in by_file.items():
        try:
            rewrite(path, file_hits, names)
        except OSError as e:
            failed = {h.finding.id for h in file_hits}
            moved = [m for m in moved if m.id not in failed]
            why = "it is read-only" if isinstance(e, PermissionError) else (e.strerror or str(e))
            skipped += [
                Skipped(
                    h.finding.id,
                    h.finding.source,
                    h.finding.resource,
                    f"couldn't be rewritten: {why}",
                    name=names[h.finding.id],
                    stored=True,
                )
                for h in file_hits
            ]
    return moved, skipped, stored


def _audit(f: Finding, *, name: str | None = None, ref: str | None = None) -> dict[str, str]:
    details = {"source": f.source, "resource": f.resource, "key": f.key}
    if name:
        details["name"] = name
    if ref:
        details["ref"] = ref
    if f.path:
        details["path"] = f.path
    if f.field:
        details["field"] = f.field
    return details


def _credential(h: Hit) -> tuple[str | None, str]:
    """What a hit stores, and the scheme its header keeps: a header's
    ``Bearer <key>`` stores the key; an environment value is stored as is."""
    if h.finding.field == "env":
        return None, h.value
    return split_scheme(h.value)


def _with_refs(config: dict[str, Any], hits: list[Hit], refs: dict[str, str]) -> dict[str, Any]:
    """``config`` without the plaintext entries, citing ``refs`` under the same
    keys, a header's scheme kept on its slot."""
    new = copy.deepcopy(config)
    transport = new["transport"]
    for h in hits:
        bucket = "env" if h.finding.field == "env" else "headers"
        transport.get(bucket, {}).pop(h.finding.key, None)
        transport.setdefault("secret_refs", {})[h.finding.key] = refs[h.finding.id]
        scheme, _ = _credential(h)
        if scheme:
            transport.setdefault("auth_schemes", {})[h.finding.key] = scheme
    return new


async def _move_server(
    uid: str,
    hits: list[Hit],
    store: SecretStore,
    update_config: UpdateConfig,
    set_note: SetNote,
) -> tuple[list[Moved], list[Skipped], list[dict[str, str]]]:
    first = hits[0].finding
    refs = {h.finding.id: secret_ref(mint_secret_name()) for h in hits}
    written: list[str] = []

    def skip_all(why: str) -> tuple[list[Moved], list[Skipped], list[dict[str, str]]]:
        for ref in written:
            store.delete(ref)
        return [], [Skipped(h.finding.id, "mcp_server", first.resource, why) for h in hits], []

    try:
        for h in hits:
            ref = refs[h.finding.id]
            _, value = _credential(h)
            await asyncio.to_thread(store.set, ref, value)
            written.append(ref)
            if await asyncio.to_thread(store.peek, ref) != value:
                return skip_all("the store did not read the value back")
            await asyncio.to_thread(set_note, ref, SecretNote(created_for=uid))
        assert hits[0].config is not None
        await update_config(uid, _with_refs(hits[0].config, hits, refs))
    except Exception as e:
        # The class name only: a validation error's text can quote a value.
        return skip_all(f"the server's config could not be changed ({type(e).__name__})")
    moved = [
        Moved(h.finding.id, "mcp_server", first.resource, None, refs[h.finding.id]) for h in hits
    ]
    stored = [_audit(h.finding, ref=refs[h.finding.id]) for h in hits]
    return moved, [], stored


async def move(
    hits: list[Hit],
    ids: Iterable[str] | None,
    *,
    store: SecretStore,
    rewrite: RewriteFile,
    update_config: UpdateConfig,
    set_note: SetNote,
    dry_run: bool = False,
) -> ImportResult:
    """Move the chosen findings (all, when ``ids`` is None) into the store.

    A dry run changes and stores nothing; it lists what would move.
    """
    wanted = None if ids is None else set(ids)
    chosen = [h for h in hits if wanted is None or h.finding.id in wanted]
    skill_hits = [h for h in chosen if h.finding.source == "skill"]
    server_hits = [h for h in chosen if h.finding.source == "mcp_server"]
    moved, skipped, stored = await asyncio.to_thread(
        _move_skills, skill_hits, store, rewrite, dry_run, set_note
    )
    groups: dict[str, list[Hit]] = {}
    for h in server_hits:
        groups.setdefault(h.finding.resource_uid or "", []).append(h)
    for uid, group in groups.items():
        if dry_run:
            moved += [
                Moved(h.finding.id, "mcp_server", h.finding.resource, None, None) for h in group
            ]
            continue
        m, s, a = await _move_server(uid, group, store, update_config, set_note)
        moved += m
        skipped += s
        stored += a
    return ImportResult(moved=moved, skipped=skipped, dry_run=dry_run, stored=stored)
