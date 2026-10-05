"""Move every secret to a minted id, once (spec secret "Move every secret to a
fixed id once").

A secret's id is ``secret/<uuid4 hex>``. Secrets stored before that rule hold
names a person or a UI once chose (``secret/github``, ``postman.AUTHORIZATION``,
``channel/telegram/bot-token``). At daemon start each is *copied, repointed,
deleted*, in an order that leaves the old ref cited until the new one is proven:

1. write the value at the new ref and read it back;
2. carry this machine's records (bindings, creation time, last-used stamp) and
   the secret's notes, naming a standalone secret after its old name;
3. repoint every citing resource through the resource service, the sync remote
   and, for a standalone secret, every ``coffer://secret/<old>`` in the skill
   master store's files;
4. delete the old ref and audit ``secret_migrated``.

A stored ref nothing cites any more is moved too, labelled with its old ref, so
no secret is left under an old name. A citer's config that still carries a key
its kind dropped long ago (``auto_enable_new_capabilities``) is written without
it: the resource service would refuse the repointed config otherwise.

A failure before any citer changed removes the new ref; one part-way keeps the
old ref in place (and the new one, which something now cites) and logs. A
second start finds nothing to move. A value is never logged or audited.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Callable
from typing import Any, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.secret.notes import SecretNotesPort
from coffer.domain.audit import AuditEventType
from coffer.domain.model_proxy.state import PROXY_TOKEN_REF_PREFIX
from coffer.domain.resource import Resource
from coffer.domain.secrets import (
    LABEL_MAX,
    ORIGIN_DIALOG,
    ORIGIN_PAGE,
    SecretNote,
    is_minted_ref,
    mint_secret_name,
    secret_ref,
    standalone_name,
)

_log = logging.getLogger(__name__)
_ACTOR = "coffer"
#: Config keys a kind no longer reads that older files still carry.
_DROPPED_KEYS: dict[str, tuple[str, ...]] = {"mcp_server": ("auto_enable_new_capabilities",)}


class RefStore(Protocol):
    def set(self, ref: str, value: str) -> None: ...
    def peek(self, ref: str) -> str | None: ...
    def delete(self, ref: str) -> None: ...
    def list_refs(self) -> list[tuple[str, str, str]]: ...
    def carry_records(self, old: str, new: str) -> None: ...


class NotesPort(Protocol):
    def get(self, ref: str) -> SecretNote | None: ...
    def put(
        self, ref: str, note: SecretNote | None, *, summary: str, actor: str | None
    ) -> None: ...


class Citations(Protocol):
    async def settled(self) -> None: ...
    def resource_citers(self) -> dict[str, list[str]]: ...
    def skill_citers(self, ref: str) -> list[str]: ...


class ExtraCiter(Protocol):
    """A setting outside the resource framework that cites a secret (the sync
    remote's push token)."""

    def ref(self) -> str | None: ...
    def repoint(self, new: str) -> None: ...


#: ``(old name, new name) -> files rewritten`` in the skill master store.
RewriteUris = Callable[[str, str], int]
#: ``(old ref, new ref)`` — carry the secret boundary's approvals.
Rebind = Callable[[str, str], None]


def _repointed(
    resource: Resource, resources: ResourceService, old: str, new: str
) -> dict[str, Any]:
    config = copy.deepcopy(resource.config)
    for dropped in _DROPPED_KEYS.get(resource.kind, ()):
        config.pop(dropped, None)
    for key, ref in resources.secret_slots(resource).items():
        if ref != old:
            continue
        if resource.kind == "mcp_server":
            config["transport"]["secret_refs"][key] = new
        else:
            config[key] = new
    return config


class RefMigrator:
    def __init__(
        self,
        resources: ResourceService,
        store: RefStore,
        notes: SecretNotesPort,
        citations: Citations,
        audit: AuditService,
        *,
        rewrite_uris: RewriteUris,
        rebind: Rebind,
        extras: list[ExtraCiter] | None = None,
    ) -> None:
        self._resources = resources
        self._store = store
        self._notes = notes
        self._citations = citations
        self._audit = audit
        self._rewrite_uris = rewrite_uris
        self._rebind = rebind
        self._extras = extras or []

    async def run(self) -> int:
        """Move every ref not yet a minted id; how many moved. Idempotent. One
        failure is logged and does not stop the rest."""
        await self._citations.settled()
        stored = {r for r, _c, _u in await asyncio.to_thread(self._store.list_refs)}
        cited = set(self._citations.resource_citers())
        cited |= {r for e in self._extras if (r := e.ref())}
        moved = 0
        for ref in sorted(stored | cited):
            if is_minted_ref(ref) or ref.startswith(PROXY_TOKEN_REF_PREFIX):
                continue
            if ref not in stored:
                _log.warning("secret.migrate_skipped", extra={"ref": ref, "reason": "not stored"})
                continue
            try:
                if await self._move(ref):
                    moved += 1
            except Exception as e:
                # The class name only: an error's text can quote a value.
                _log.warning("secret.migrate_failed", extra={"ref": ref, "error": type(e).__name__})
        return moved

    async def _move(self, old: str) -> bool:
        uids = list(dict.fromkeys(self._citations.resource_citers().get(old, [])))
        name = standalone_name(old)
        extras = [e for e in self._extras if e.ref() == old]
        # Nothing cites an orphan: its old ref is the only hint of what it was.
        orphan = not name and not uids and not extras
        value = await asyncio.to_thread(self._store.peek, old)
        if value is None:
            return False
        new = secret_ref(mint_secret_name())
        changed = 0
        try:
            await asyncio.to_thread(self._store.set, new, value)
            if await asyncio.to_thread(self._store.peek, new) != value:
                raise RuntimeError("the store did not read the value back")
            await asyncio.to_thread(self._store.carry_records, old, new)
            await asyncio.to_thread(self._rebind, old, new)
            await asyncio.to_thread(self._carry_notes, old, new, name, uids, orphan)
            for uid in uids:
                current = await self._resources.get(uid)
                await self._resources.update_config(
                    uid,
                    _repointed(current, self._resources, old, new),
                    _ACTOR,
                    allow_lifecycle_kind=True,
                )
                changed += 1
            for extra in extras:
                await asyncio.to_thread(extra.repoint, new)
                changed += 1
            # Repointing citers one at a time let the first claim the new ref as
            # minted for it; a ref several resources share belongs to none.
            await asyncio.to_thread(self._carry_notes, old, new, name, uids, orphan)
            if name:
                await asyncio.to_thread(self._rewrite_uris, name, mint_name_of(new))
        except BaseException:
            if changed == 0:
                # Nothing cites the new ref yet: deleting it forgets its records.
                await asyncio.to_thread(self._store.delete, new)
            else:
                _log.warning("secret.migrate_partial", extra={"from": old, "to": new})
            raise
        await asyncio.to_thread(self._store.delete, old)
        await self._audit.record(
            AuditEventType.SECRET_MIGRATED.value, actor=_ACTOR, details={"from": old, "to": new}
        )
        _log.info("secret.migrated", extra={"from": old, "to": new})
        return True

    def _carry_notes(
        self, old: str, new: str, name: str | None, uids: list[str], orphan: bool
    ) -> None:
        before = self._notes.get(old) or SecretNote()
        hint = name or (old if orphan else None)
        label = before.label or (hint[:LABEL_MAX] if hint else None)
        created_for = before.created_for or (uids[0] if len(uids) == 1 and not name else None)
        note = SecretNote(
            label=label,
            description=before.description,
            created_for=created_for,
            # A standalone secret was a person's; a resource's was written for it.
            origin=before.origin or (ORIGIN_PAGE if name or orphan else ORIGIN_DIALOG),
        )
        if not note.empty:
            self._notes.put(new, note, summary=f"carry notes of secret {old}", actor=_ACTOR)


def mint_name_of(ref: str) -> str:
    return ref.removeprefix("secret/")
