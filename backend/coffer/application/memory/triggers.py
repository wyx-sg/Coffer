"""Memory triggers: listing, writing, proposing, arming and removing them (spec
memory "Keep triggers in the vault, armed only by a person").

A trigger is authored, so it has two ways in and one way to take effect:

* a **person** writes one (REST ``POST /memory/triggers`` or
  ``coffer memory trigger add``) — it is armed by that person as it is written;
* **distil** proposes one while rewriting a note it judges a known trap tied to a
  command — it lands unarmed, as a proposal, and does nothing;
* only a person **arms** a proposal (``arm``); ``disarm`` returns a trigger to a
  proposal, ``delete`` removes its file.

Nothing is seeded: a fresh vault has no triggers until a person writes or arms
one. Every act is an audit event naming the trigger and its note.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.trigger import KIND_BLOCK, Trigger, TriggerInvalid, validate
from coffer.infrastructure.memory import trigger_store

#: Actors that are not a person, and so may propose but never arm.
MACHINE_ACTORS = frozenset({"distil", "system"})
PROPOSER_DISTIL = "distil"


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _new_id(slug: str) -> str:
    stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug.lower()).strip("-_")
    return f"{(stem or 'trigger')[:40].strip('-_') or 'trigger'}-{secrets.token_hex(3)}"


@dataclass(frozen=True)
class TriggerDraft:
    """What a person or distil supplies; the rest is Coffer's bookkeeping."""

    note: str
    kind: str = KIND_BLOCK
    command: str = ""
    unless: str = ""
    error: str = ""
    body: str = ""


class TriggerService:
    def __init__(self, *, audit: AuditService) -> None:
        self._audit = audit

    def all(self) -> list[Trigger]:
        return trigger_store.list_triggers()

    def armed(self) -> list[Trigger]:
        return [t for t in trigger_store.list_triggers() if t.armed]

    def get(self, trigger_id: str) -> Trigger:
        return trigger_store.read_trigger(trigger_id)

    def _build(self, draft: TriggerDraft, *, armed_by: str, proposed_by: str) -> Trigger:
        slug = draft.note.split("/", 1)[-1]
        stamp = _now()
        return validate(
            Trigger(
                id=_new_id(slug),
                note=draft.note.strip(),
                kind=draft.kind,
                command=draft.command,
                unless=draft.unless,
                error=draft.error,
                armed_by=armed_by,
                armed_at=stamp if armed_by else "",
                proposed_by=proposed_by,
                created=stamp,
                body=draft.body,
            )
        )

    async def _record(self, event: AuditEventType, trigger: Trigger, actor: str) -> None:
        await self._audit.record(
            event.value,
            actor=actor,
            details={"trigger": trigger.id, "note": trigger.note, "kind": trigger.kind},
        )

    async def add(self, draft: TriggerDraft, *, actor: str) -> Trigger:
        """A trigger a person wrote: armed by them as it is written."""
        _require_person(actor)
        trigger = self._build(draft, armed_by=actor, proposed_by="")
        trigger_store.write_trigger(trigger)
        await self._record(AuditEventType.MEMORY_TRIGGER_ADDED, trigger, actor)
        return trigger

    async def propose(
        self, draft: TriggerDraft, *, proposer: str = PROPOSER_DISTIL
    ) -> Trigger | None:
        """A proposal, unarmed; ``None`` when one with the same note and
        patterns already exists, armed or not."""
        for existing in trigger_store.list_triggers():
            if (existing.note, existing.kind, existing.command, existing.error) == (
                draft.note,
                draft.kind,
                draft.command,
                draft.error,
            ):
                return None
        try:
            trigger = self._build(draft, armed_by="", proposed_by=proposer)
        except TriggerInvalid:
            return None
        trigger_store.write_trigger(trigger)
        await self._record(AuditEventType.MEMORY_TRIGGER_PROPOSED, trigger, proposer)
        return trigger

    async def arm(self, trigger_id: str, *, actor: str) -> Trigger:
        _require_person(actor)
        trigger = trigger_store.read_trigger(trigger_id).arm(actor, _now())
        trigger_store.write_trigger(trigger)
        await self._record(AuditEventType.MEMORY_TRIGGER_ARMED, trigger, actor)
        return trigger

    async def disarm(self, trigger_id: str, *, actor: str) -> Trigger:
        trigger = trigger_store.read_trigger(trigger_id).disarm()
        trigger_store.write_trigger(trigger)
        await self._record(AuditEventType.MEMORY_TRIGGER_DISARMED, trigger, actor)
        return trigger

    async def delete(self, trigger_id: str, *, actor: str) -> None:
        trigger = trigger_store.read_trigger(trigger_id)
        trigger_store.delete_trigger(trigger_id)
        await self._record(AuditEventType.MEMORY_TRIGGER_DELETED, trigger, actor)


def _require_person(actor: str) -> None:
    if actor in MACHINE_ACTORS:
        raise TriggerInvalid(f"only a person arms a memory trigger, not {actor!r}")


__all__ = ["MACHINE_ACTORS", "PROPOSER_DISTIL", "TriggerDraft", "TriggerService"]
