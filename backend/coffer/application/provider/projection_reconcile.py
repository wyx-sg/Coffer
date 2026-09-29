"""A provider connection's projection into each agent, as a reconcile target.

ADR one-level-triggered-reconciler-compares-parameters. ``is_active`` is a flag
in Coffer's database; what it means is a handful of keys inside a file Coffer
does not own — ``settings.json``, Codex's ``config.toml`` and the model
catalogue beside it. Those files are rewritten by their own CLIs, by other
tooling, by the user and by restores from backup. This target judges each
enabled agent's file by every key Coffer owns in it (``projection_params``),
against what projecting the active connection would write now — so a base
URL, model, ``apiKeyHelper`` command or catalogue that no longer matches is a
difference exactly as a missing projection is. The boot heal it replaces
looked at presence alone.

**Direction policy** (spec provider-switching "Clear an active flag the
agent's config contradicts", "Converge connections across machines"):

- keys present, values differ → re-project (``projection_stale``);
- active connection, keys absent → project when the pass carries a warrant
  (a sync import brought the switch from another machine, or a person asked),
  or when another agent of the same type does carry the keys (the activation
  took effect); otherwise the flag is what is stale — Coffer clears its own
  record (``ProviderService.deactivate``) and never re-routes an agent on a
  leftover flag (``flag_contradicted``);
- keys present, nothing active reaches the agent → reported only
  (``projection_unclaimed``): removing them would change what the agent talks
  to. Removed under the same warrant as above.

A file that cannot be read or does not parse is skipped on both sides and
blocks clearing the flag for its type: guessing "absent" from a file Coffer
could not inspect would clear a flag on no evidence.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.application.provider.projector import Priors, ProviderProjector
from coffer.application.provider.targets import projection_targets
from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.provider.agent_projection import ProviderProjection
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.projection_params import (
    digest,
    flatten,
    owned_keys,
    params_of,
    parse_document,
    render,
)
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

_log = logging.getLogger(__name__)

TARGET = "provider_projection"
#: The triggers that carry a warrant to change what an agent talks to.
_WARRANTED = frozenset({Trigger.IMPORT, Trigger.MANUAL})

#: ``ProviderService.deactivate`` — clears the flag, audits the switch itself.
Deactivate = Callable[[AgentType], Awaitable[object]]


class _Lister(Protocol):
    async def list(self) -> list[Resource]: ...


class _Store(Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(
        self, path: pathlib.Path, text: str, *, expected_fingerprint: str | None = None
    ) -> None: ...
    def delete_with_backup(self, path: pathlib.Path) -> bool: ...


@dataclass(frozen=True)
class _Seen:
    """One enabled agent, its file, and both sides of the comparison."""

    agent: Resource
    agent_type: AgentType
    path: pathlib.Path
    #: The active connection reaching this agent, if any.
    connection: tuple[Resource, ProviderConfig] | None
    desired: dict[str, Any] | None
    observed: dict[str, Any] | None


@dataclass
class _Scan:
    seen: dict[str, _Seen]
    #: Types where some enabled agent's file carries Coffer's keys.
    carried: set[AgentType]
    #: Types where some enabled agent's file could not be judged.
    unreadable: set[AgentType]


def _title(r: Resource) -> str:
    return r.title or r.name


class ProviderProjectionTarget:
    """Implements ``ReconcileTarget`` for provider projections."""

    name = TARGET
    kinds = frozenset({"provider", "agent"})

    def __init__(
        self,
        *,
        providers: _Lister,
        agents: _Lister,
        projector: ProviderProjector,
        store: _Store,
        deactivate: Deactivate,
    ) -> None:
        self._providers = providers
        self._agents = agents
        self._projector = projector
        self._store = store
        self._deactivate = deactivate
        #: The last scan's per-type facts, which ``decide`` reads: a matching
        #: agent makes no difference, yet it still says the activation took.
        self._last = _Scan({}, set(), set())

    # --- reading ---------------------------------------------------------------

    async def _enabled_agents(self) -> list[tuple[Resource, AgentConfig]]:
        out: list[tuple[Resource, AgentConfig]] = []
        for row in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(row.config)
            except Exception:
                continue  # surfaced by the agent routes; never stops a pass
            out.append((row, cfg))
        return out

    async def _active(
        self, agents: list[Resource]
    ) -> tuple[dict[AgentType, tuple[Resource, ProviderConfig]], dict[str, Resource]]:
        """The active connection per agent type (sorted by name, first wins,
        so a transient double-active state resolves deterministically), and
        every connection by uid."""
        active: dict[AgentType, tuple[Resource, ProviderConfig]] = {}
        by_uid: dict[str, Resource] = {}
        for row in sorted(await self._providers.list(), key=lambda r: r.name):
            by_uid[row.uid] = row
            try:
                cfg = ProviderConfig.model_validate(row.config)
            except Exception:
                continue
            if not cfg.is_active:
                continue
            for agent_type in projection_targets(row, cfg, agents):
                active.setdefault(agent_type, (row, cfg))
        return active, by_uid

    async def _scan(self) -> _Scan:
        rows = await self._enabled_agents()
        active, by_uid = await self._active([r for r, _ in rows])
        scan = _Scan({}, set(), set())
        for row, cfg in rows:
            facet = self._projector.projection_for(cfg.type)
            if not row.enabled or facet is None:
                continue
            if not cfg.resolved_config_dir().is_dir():
                # A stale row whose config dir vanished is not resurrected by
                # a projection write (mkdir -p).
                continue
            try:
                seen = self._judge(row, cfg, facet, active.get(cfg.type), by_uid)
            except Exception as exc:  # unreadable or unparseable: never guessed from
                _log.warning("provider_projection: %s left alone: %r", row.name, exc)
                scan.unreadable.add(cfg.type)
                continue
            scan.seen[row.uid] = seen
            if seen.observed is not None:
                scan.carried.add(cfg.type)
        self._last = scan
        return scan

    def _judge(
        self,
        row: Resource,
        cfg: AgentConfig,
        facet: ProviderProjection,
        connection: tuple[Resource, ProviderConfig] | None,
        by_uid: dict[str, Resource],
    ) -> _Seen:
        spec = spec_for(cfg.type, facet.config_key, cfg.resolved_config_dir())
        fmt = spec.format.value
        current = self._store.read_text(spec.path) or ""
        cur = flatten(parse_document(fmt, current))
        stripped = facet.remove(current, spec.path)
        base = flatten(parse_document(fmt, stripped.text))
        present = facet.is_present(current)

        want: dict[str, Any] | None = None
        want_flat: dict[str, Any] = {}
        want_files: dict[str, str | None] = {}
        if connection is not None:
            conn, ccfg = connection
            request = self._projector.request_for(conn, ccfg, cfg)
            plan = facet.apply(current, request, spec.path)
            want_flat = flatten(parse_document(fmt, plan.text))
            want_files = {f"file:{s.path.name}": digest(s.text) for s in plan.before + plan.after}
        keys = owned_keys(want_flat, base) if connection is not None else set()
        if present:
            keys |= owned_keys(cur, base)
        if connection is not None:
            want = {**params_of(want_flat, keys), **want_files, "connection": connection[0].uid}

        have: dict[str, Any] | None = None
        if present:
            side_paths = {s.path for s in stripped.before + stripped.after}
            if connection is not None:
                side_paths |= {spec.path.parent / n.split(":", 1)[1] for n in want_files}
            files = {f"file:{p.name}": digest(self._store.read_text(p)) for p in side_paths}
            have = {**params_of(cur, keys), **files}
            have["connection"] = self._named_connection(have, want, by_uid)
        return _Seen(row, cfg.type, spec.path, connection, want, have)

    @staticmethod
    def _named_connection(
        have: dict[str, Any], want: dict[str, Any] | None, by_uid: dict[str, Resource]
    ) -> str | None:
        """The connection the file names: a uid one of its values carries (the
        ``apiKeyHelper``); else the wanted connection, when every key whose
        wanted value names it (Codex's provider label) holds what it writes."""
        for value in have.values():
            if isinstance(value, str):
                for uid in by_uid:
                    if uid in value:
                        return uid
        if want is None:
            return None
        uid = str(want["connection"])
        row = by_uid.get(uid)
        labels = [uid] + ([row.name] if row is not None and row.name else [])
        naming = [
            k
            for k, v in want.items()
            if k != "connection" and isinstance(v, str) and any(n in v for n in labels)
        ]
        if naming and all(have.get(k) == want[k] for k in naming):
            return uid
        return None

    # --- the target --------------------------------------------------------------

    async def desired(self) -> Sequence[Item]:
        scan = await self._scan()
        return [self._item(s, s.desired) for s in scan.seen.values() if s.desired is not None]

    async def observe(self) -> Sequence[Item]:
        scan = await self._scan()
        return [self._item(s, s.observed) for s in scan.seen.values() if s.observed is not None]

    @staticmethod
    def _item(seen: _Seen, params: dict[str, Any]) -> Item:
        return Item(
            key=seen.agent.uid,
            subject=Subject("agent", seen.agent.uid, _title(seen.agent)),
            params=params,
            file=str(seen.path),
            text=render(params),
        )

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        scan = self._last
        warranted = trigger in _WARRANTED
        out: list[Decision] = []
        for d in differences:
            seen = scan.seen.get(d.key)
            agent_type = seen.agent_type if seen is not None else None
            if d.op is Op.MODIFY:
                names = ", ".join(d.changed_params)
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "projection_stale",
                        f"The projection's {names} differ from what the active connection "
                        "writes; it is projected again.",
                    )
                )
            elif d.op is Op.REMOVE:
                out.append(
                    Decision(
                        Disposition.REPAIR if warranted else Disposition.REPORT,
                        "projection_unclaimed",
                        "Coffer's keys are in the agent's config but no active connection "
                        "reaches it; removing them would change what the agent talks to.",
                    )
                )
            elif warranted or agent_type in scan.carried:
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "projection_missing",
                        "The active connection is not projected into this agent; it is projected.",
                    )
                )
            elif agent_type in scan.unreadable:
                out.append(
                    Decision(
                        Disposition.BLOCKED,
                        "config_unreadable",
                        "Another agent of this type has a config Coffer cannot read, so "
                        "whether the connection is in use cannot be told.",
                    )
                )
            else:
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "flag_contradicted",
                        "The connection is marked active but no agent of this type carries "
                        "it; Coffer clears its own flag and the agent stays on its "
                        "built-in login.",
                    )
                )
        return out

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        seen = (await self._scan()).seen.get(d.key)
        if seen is None:
            raise LookupError(f"agent {d.key} is no longer judged by this target")
        reason = change.decision.reason_code
        if reason == "flag_contradicted":
            # Audited by the service itself (PROVIDER_SWITCHED); nothing of the
            # agent's is written.
            await self._deactivate(seen.agent_type)
            return Applied(event=None)
        details: dict[str, Any] = {
            "agent": seen.agent.name,
            "agent_uid": seen.agent.uid,
            "path": str(seen.path),
            "repaired": list(d.changed_params),
            "reason": reason,
        }
        if d.op is Op.REMOVE:
            priors = self._projector.deproject_agent(seen.agent)
            event = AuditEvent(
                AuditEventType.PROVIDER_PROJECTION_REPAIRED.value,
                seen.agent,
                {**details, "action": "deproject"},
            )
            return Applied(event, undo=self._restore(priors))
        if seen.connection is None:
            raise LookupError(f"no active connection reaches agent {seen.agent.name}")
        connection, cfg = seen.connection
        priors = self._projector.project_agent(connection, cfg, seen.agent)
        event = AuditEvent(
            AuditEventType.PROVIDER_PROJECTION_REPAIRED.value,
            connection,
            {**details, "action": "project", "connection": connection.name},
        )
        return Applied(event, undo=self._restore(priors))

    def _restore(self, priors: Priors) -> Undo:
        """Put back every file the write touched — delete one it created."""

        async def _undo() -> None:
            for path, before in priors.items():
                if before is None:
                    self._store.delete_with_backup(path)
                else:
                    self._store.write_text_atomic(path, before)

        return _undo


__all__ = ["TARGET", "Deactivate", "ProviderProjectionTarget"]
