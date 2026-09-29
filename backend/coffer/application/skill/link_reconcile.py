"""Skill delivery links, as one reconcile target.

ADR one-level-triggered-reconciler-compares-parameters. A skill reaches an
agent as a directory link ``<agent skill dir>/<skill name>`` to the skill's
master folder, recorded by a ``skill_agent_bindings`` row. This target is the
one place that decides and performs that delivery; every trigger — daemon
boot, the period, a skill's ``enabled`` / ``scope`` edit, an agent registered,
switched or moved, an import, the builtin seed, ``coffer skill verify --fix``
— asks the reconciler for a pass over it.

**What is wanted.** One rule, and nothing else decides it::

    delivered(skill, agent) == agent.enabled and skill.enabled
                               and scope.is_active(skill.scope, agent.uid)

for every agent whose config parses. Each wanted delivery is an item keyed
``<skill_uid>@<agent_uid>`` whose parameters are the link path, the master it
points at, ``state: ok`` and ``bound: True`` (a binding row records it).

**What is there.** Every enabled binding row, judged on disk
(``SyncEngine.classify_target``): ``state`` is ``ok`` or the drift kind. A
wanted delivery with no row is observed too when its path is already occupied
— by a correct link nobody recorded (``bound: False``, repaired by recording
it), or by foreign content, which becomes a *blocked* difference rather than
a write that would fail. Master folders no row claims are observed-only
``orphan:<name>`` items.

**Direction policy.** Missing and tampered links are repaired (a tampered one
is renamed aside to ``<path>.coffer-backup-<ts>`` first); a delivery whose
agent's config dir moved is relinked; one no longer wanted is reclaimed.
Foreign content is never clobbered, under any trigger, and a missing master
has nothing to link to: both are blocked. An orphan master is only reported.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.reconcile.ports import Applied, AuditEvent
from coffer.application.skill import binding_ops
from coffer.domain.audit import AuditEventType
from coffer.domain.reconcile import (
    Decision,
    Difference,
    Disposition,
    Item,
    Op,
    PlannedChange,
    Subject,
    Trigger,
)
from coffer.domain.resource import Resource
from coffer.domain.scope import is_active
from coffer.domain.skill.binding import BindingState
from coffer.domain.skill.drift import DriftKind

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

TARGET = "skill_link"
ORPHAN_PREFIX = "orphan:"
OK = "ok"
#: The agent's config dir is gone, so linking would recreate it out of nothing.
AGENT_DIR_MISSING = "agent_dir_missing"


@dataclass(frozen=True)
class _World:
    """One read of Coffer's own state, shared by a desired/observe pair."""

    skills: dict[int, Resource]
    agents: dict[int, Resource]
    #: Agent uid → its skills directory, for agents whose config parses.
    skill_dirs: dict[str, pathlib.Path]
    bindings: list[BindingState]

    def wanted(self) -> dict[str, tuple[Resource, Resource, pathlib.Path]]:
        """``key → (skill, agent, link)`` for every delivery the rule grants,
        ordered by agent name then skill name (uids are random)."""
        out: dict[str, tuple[Resource, Resource, pathlib.Path]] = {}
        skills = sorted(self.skills.values(), key=lambda s: s.name)
        for agent in sorted(self.agents.values(), key=lambda a: a.name):
            skill_dir = self.skill_dirs.get(agent.uid)
            if not agent.enabled or skill_dir is None:
                continue
            for skill in skills:
                if skill.enabled and is_active(skill.scope, agent.uid):
                    out[key_for(skill, agent)] = (skill, agent, skill_dir / skill.name)
        return out


def key_for(skill: Resource, agent: Resource) -> str:
    return f"{skill.uid}@{agent.uid}"


def split_key(key: str) -> tuple[str, str]:
    skill_uid, _, agent_uid = key.partition("@")
    return skill_uid, agent_uid


def _subject(skill: Resource) -> Subject:
    return Subject("skill", skill.uid, skill.title or skill.name)


def _item(
    key: str, skill: Resource, link: pathlib.Path, master: pathlib.Path, state: str, bound: bool
) -> Item:
    params = {"link": str(link), "target": str(master), "state": state, "bound": bound}
    text = f"{link} -> {master}" if state == OK else f"{link} -> {master} ({state})"
    return Item(key, _subject(skill), params, file=str(link), text=text)


def _occupied(path: pathlib.Path) -> bool:
    return path.exists() or path.is_symlink()


class SkillLinkTarget:
    """Implements ``ReconcileTarget`` for delivered skill links."""

    name = TARGET
    kinds = frozenset({"skill", "agent"})

    def __init__(self, *, service: SkillService) -> None:
        self._svc = service

    # --- reading ---------------------------------------------------------------

    async def _world(self) -> _World:
        rs = self._svc._rs
        skills = {s.id: s for s in await rs.list(kind="skill")}
        agents = {a.id: a for a in await rs.list(kind="agent")}
        skill_dirs: dict[str, pathlib.Path] = {}
        for agent in agents.values():
            try:
                skill_dirs[agent.uid] = self._svc._resolve_agent_skill_dir(agent)
            except Exception:  # a config that does not parse delivers nothing
                continue
        return _World(skills, agents, skill_dirs, await self._svc._bindings.list_all())

    def _master(self, skill: Resource) -> pathlib.Path:
        return pathlib.Path(self._svc._store.paths_for(skill.name).folder)

    def _state(self, link: pathlib.Path, master: pathlib.Path, binding: BindingState | None) -> str:
        status = self._svc._sync.classify_target(
            link=link, expected_master=master, link_mode=binding.link_mode if binding else None
        )
        if status.drift is None:
            return OK
        if status.drift is DriftKind.MISSING_LINK and not link.parent.parent.is_dir():
            return AGENT_DIR_MISSING
        return str(status.drift.value)

    # --- the target ------------------------------------------------------------

    async def desired(self) -> Sequence[Item]:
        return [
            _item(key, skill, link, self._master(skill), OK, True)
            for key, (skill, _agent, link) in (await self._world()).wanted().items()
        ]

    async def observe(self) -> Sequence[Item]:
        world = await self._world()
        wanted = world.wanted()
        items: list[Item] = []
        seen: set[str] = set()
        for b in world.bindings:
            skill = world.skills.get(b.skill_resource_id)
            agent = world.agents.get(b.agent_resource_id)
            if not b.enabled or skill is None or agent is None:
                continue
            key = key_for(skill, agent)
            master = self._master(skill)
            want = wanted.get(key)
            if b.last_link_path:
                link = pathlib.Path(b.last_link_path)
            elif want is not None:
                link = want[2]
            else:
                continue
            seen.add(key)
            new_link = want[2] if want is not None else link
            if (
                new_link != link
                and _occupied(new_link)
                and self._state(new_link, master, None) != OK
            ):
                # The agent moved, and its new skills dir already holds foreign
                # content where the link would go.
                state, link = DriftKind.REPLACED_WITH_REGULAR.value, new_link
            else:
                state = self._state(link, master, b)
            items.append(_item(key, skill, link, master, state, True))
        for key, (skill, _agent, link) in wanted.items():
            if key in seen:
                continue
            master = self._master(skill)
            if not master.is_dir():
                state = DriftKind.MISSING_MASTER.value
            elif _occupied(link):
                ok = self._state(link, master, None) == OK
                state = OK if ok else DriftKind.REPLACED_WITH_REGULAR.value
            elif not link.parent.parent.is_dir():
                state = AGENT_DIR_MISSING
            else:
                continue  # nothing there: an ADD
            items.append(_item(key, skill, link, master, state, False))
        known = {s.name for s in world.skills.values()}
        for name in sorted(self._svc._store.find_orphans(known)):
            folder = pathlib.Path(self._svc._store.paths_for(name).folder)
            items.append(
                Item(
                    f"{ORPHAN_PREFIX}{name}",
                    Subject("skill", None, name),
                    {"target": str(folder), "state": DriftKind.ORPHAN_MASTER.value},
                    file=str(folder),
                    text=f"{folder} (no Coffer record)",
                )
            )
        return items

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        return [_decide(d) for d in differences]

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        code = change.decision.reason_code
        skill_uid, agent_uid = split_key(d.key)
        skill = await self._svc._rs.get(skill_uid)
        agent = await self._svc._rs.get(agent_uid)
        svc = self._svc
        if code == "reclaim":
            write = await binding_ops.reclaim(svc, skill=skill, agent=agent)
            event = AuditEventType.SKILL_UNBOUND
            details: dict[str, object] = {"agent": agent.name}
        else:
            assert d.desired is not None
            link = pathlib.Path(d.desired.params["link"])
            if code == "link_moved":
                assert d.observed is not None
                old = pathlib.Path(d.observed.params["link"])
                write = await binding_ops.relink(
                    svc, skill=skill, agent=agent, old_link=old, new_link=link
                )
                event = AuditEventType.SKILL_RELINKED
                details = {"agent": agent.name, "link": str(link), "from": str(old)}
            elif code in (DriftKind.MISSING_LINK.value, DriftKind.TAMPERED_LINK.value):
                write = await binding_ops.deliver(
                    svc,
                    skill=skill,
                    agent=agent,
                    link=link,
                    back_up_existing=code == DriftKind.TAMPERED_LINK.value,
                )
                event = AuditEventType.SKILL_DRIFT_REMEDIATED
                details = {"agent": agent.name, "kind": code}
                if write.backup is not None:
                    details["backup"] = str(write.backup)
            elif code in ("deliver", "unrecorded_link"):
                write = await binding_ops.deliver(svc, skill=skill, agent=agent, link=link)
                event = AuditEventType.SKILL_BOUND
                details = {
                    "agent": agent.name,
                    "link": str(link),
                    "mode": write.mode.value if write.mode else None,
                }
                if code == "unrecorded_link":
                    details["adopted"] = True
            else:  # pragma: no cover - decide() never plans another repair
                raise ValueError(f"skill_link cannot apply {code!r}")

        async def _undo() -> None:
            await binding_ops.undo(svc, write)

        # ``details`` names the agent by its LABEL at the moment of the write:
        # an audit row is a historical record (see AuditService).
        return Applied(AuditEvent(event.value, skill, details), undo=_undo)


def _decide(d: Difference) -> Decision:
    """The direction policy for one difference. Independent of the trigger:
    what is safe to repair unattended is exactly what is safe on request."""
    if d.key.startswith(ORPHAN_PREFIX):
        return Decision(
            Disposition.REPORT,
            DriftKind.ORPHAN_MASTER.value,
            "A folder in Coffer's skill store has no Coffer record; Coffer leaves it "
            "for you to add or remove.",
        )
    if d.op is Op.ADD:
        return Decision(
            Disposition.REPAIR,
            "deliver",
            "The skill is enabled and in scope for this agent but not delivered; it is "
            "linked from master.",
        )
    if d.op is Op.REMOVE:
        return Decision(
            Disposition.REPAIR,
            "reclaim",
            "The skill is no longer enabled and in scope for this agent (or the agent is "
            "switched off); its delivered link is removed.",
        )
    assert d.desired is not None and d.observed is not None
    state = d.observed.params["state"]
    if state == DriftKind.REPLACED_WITH_REGULAR.value:
        return Decision(
            Disposition.BLOCKED,
            "foreign_content",
            f"{d.observed.params['link']} holds content Coffer did not put there; Coffer "
            "never overwrites it — move it away and the link is made.",
        )
    if state == DriftKind.MISSING_MASTER.value:
        return Decision(
            Disposition.BLOCKED,
            DriftKind.MISSING_MASTER.value,
            "The skill's master folder is gone, so there is nothing to link to.",
        )
    if d.observed.params["link"] != d.desired.params["link"]:
        return Decision(
            Disposition.REPAIR,
            "link_moved",
            "The agent's config directory moved; the link is made in the new skills "
            "directory and removed from the old one.",
        )
    if state == AGENT_DIR_MISSING:
        return Decision(
            Disposition.BLOCKED,
            AGENT_DIR_MISSING,
            "The agent's config directory does not exist on this machine; Coffer does "
            "not create it to hold a link.",
        )
    if state == DriftKind.TAMPERED_LINK.value:
        return Decision(
            Disposition.REPAIR,
            DriftKind.TAMPERED_LINK.value,
            "The link points somewhere other than master; it is moved aside to a "
            "backup and linked to master again.",
        )
    if state == DriftKind.MISSING_LINK.value:
        return Decision(
            Disposition.REPAIR,
            DriftKind.MISSING_LINK.value,
            "The delivered link is gone; it is linked from master again.",
        )
    return Decision(
        Disposition.REPAIR,
        "unrecorded_link",
        "A correct link to master is already in place with no Coffer record; the "
        "delivery is recorded.",
    )


__all__ = ["ORPHAN_PREFIX", "TARGET", "SkillLinkTarget", "key_for", "split_key"]
