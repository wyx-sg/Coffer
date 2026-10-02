"""A provider connection's projection into each agent, as a reconcile target.

ADR one-level-triggered-reconciler-compares-parameters. Which connection an agent
runs on is a field of the agent's record (``AgentConfig.connection_uid``, read
through ``targets.connection_for_agent``); what it means is a handful of keys
inside a file Coffer does not own — ``settings.json``, Codex's ``config.toml``
and the model catalogue beside it. Those files are rewritten by their own CLIs,
by other tooling, by the user and by restores from backup. This target judges
each enabled agent's file by every key Coffer owns in it (``projection_params``),
against what projecting the agent's connection would write now — so a base URL,
model, ``apiKeyHelper`` command or catalogue that no longer matches is a
difference exactly as a missing projection is. The boot heal it replaces looked
at presence alone.

**Direction policy** (spec provider-switching "Clear an agent's connection its
config contradicts"):

- keys present, values differ → re-project (``projection_stale``);
- the agent is on a connection, keys absent → project when the pass carries a
  warrant (a sync import, or a person asked); otherwise the RECORD is what is
  stale: Coffer clears this one agent's own ``connection_uid``
  (``ProviderService.clear_agent_connection``, audited as the pass's repair),
  writes no agent's file, and never re-routes an agent on a leftover choice
  (``choice_contradicted``). Nothing else moves: the choice is per agent;
- keys present, the agent is on no connection → reported only
  (``projection_unclaimed``): removing them would change what the agent talks
  to. Removed under the same warrant as above.

A file that cannot be read or does not parse is skipped: guessing "absent" from
a file Coffer could not inspect would clear a choice on no evidence.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.application.provider.projection_named import named_connection
from coffer.application.provider.projector import Priors, ProviderProjector, binding_of
from coffer.application.provider.targets import connection_for_agent
from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.types import AgentType, agent_display_name
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
#: ``SWITCH`` is the ``models`` feature being switched: off withdraws Coffer's
#: keys from every agent, on projects each agent's connection again (spec
#: experimental-features "Withdraw what a switched-off feature put in front of
#: agents"). Without the warrant, switching on would read as a contradicted
#: choice and clear the agents' records.
_WARRANTED = frozenset({Trigger.IMPORT, Trigger.MANUAL, Trigger.SWITCH})

#: ``ProviderService.clear_agent_connection`` — takes an agent uid, clears that
#: agent's connection and writes nothing else.
ClearChoice = Callable[[str], Awaitable[object]]


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
    #: The connection this agent runs on, if any.
    connection: tuple[Resource, ProviderConfig] | None
    desired: dict[str, Any] | None
    observed: dict[str, Any] | None


@dataclass
class _Scan:
    seen: dict[str, _Seen]


def _title(r: Resource) -> str:
    return agent_display_name(r.config, r.name)


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
        clear_choice: ClearChoice,
        is_enabled: Callable[[], bool] = lambda: True,
    ) -> None:
        # Whether the ``models`` feature is on right now: while it is off no
        # agent is wanted on a connection, so every projection is withdrawn
        # (the agents' records keep their choice, and switching on restores it).
        self._is_enabled = is_enabled
        self._providers = providers
        self._agents = agents
        self._projector = projector
        self._store = store
        self._clear_choice = clear_choice

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

    async def _scan(self) -> _Scan:
        rows = await self._enabled_agents()
        connections = await self._providers.list()
        by_uid = {r.uid: r for r in connections}
        scan = _Scan({})
        for row, cfg in rows:
            facet = self._projector.projection_for(cfg.type)
            if not row.enabled or facet is None:
                continue
            if not cfg.resolved_config_dir().is_dir():
                # A stale row whose config dir vanished is not resurrected by
                # a projection write (mkdir -p).
                continue
            try:
                seen = self._judge(row, cfg, facet, connection_for_agent(row, connections), by_uid)
            except Exception as exc:  # unreadable or unparseable: never guessed from
                _log.warning("provider_projection: %s left alone: %r", row.name, exc)
                continue
            scan.seen[row.uid] = seen
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
        stripped = facet.remove(current, spec.path, binding_of(cfg))
        base = flatten(parse_document(fmt, stripped.text))
        present = facet.is_present(current)

        want: dict[str, Any] | None = None
        want_flat: dict[str, Any] = {}
        want_files: dict[str, str | None] = {}
        if connection is not None:
            conn, ccfg = connection
            request = self._projector.request_for(conn, ccfg, row)
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
            have["connection"] = named_connection(have, want, by_uid)
        return _Seen(row, cfg.type, spec.path, connection, want, have)

    # --- the target --------------------------------------------------------------

    async def desired(self) -> Sequence[Item]:
        if not self._is_enabled():
            return []
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
        warranted = trigger in _WARRANTED
        out: list[Decision] = []
        for d in differences:
            if d.op is Op.MODIFY:
                names = ", ".join(d.changed_params)
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "projection_stale",
                        f"The projection's {names} differ from what the agent's connection "
                        "writes; it is projected again.",
                    )
                )
            elif d.op is Op.REMOVE and not self._is_enabled():
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "feature_off",
                        "Models is switched off, so Coffer's keys are withdrawn from this agent.",
                    )
                )
            elif d.op is Op.REMOVE:
                out.append(
                    Decision(
                        Disposition.REPAIR if warranted else Disposition.REPORT,
                        "projection_unclaimed",
                        "Coffer's keys are in the agent's config but the agent runs on no "
                        "connection; removing them would change what the agent talks to.",
                    )
                )
            elif warranted:
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "projection_missing",
                        "The agent's connection is not projected into it; it is projected.",
                    )
                )
            else:
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "choice_contradicted",
                        "The agent is recorded as running on a connection but its config "
                        "carries none of Coffer's keys; Coffer clears its own record and the "
                        "agent stays on its built-in login.",
                    )
                )
        return out

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        scan = await self._scan()
        seen = scan.seen.get(d.key)
        if seen is None:
            raise LookupError(f"agent {d.key} is no longer judged by this target")
        reason = change.decision.reason_code
        details: dict[str, Any] = {
            "agent": seen.agent.name,
            "agent_uid": seen.agent.uid,
            "path": str(seen.path),
            "repaired": list(d.changed_params),
            "reason": reason,
        }
        if reason == "choice_contradicted":
            # Only Coffer's own record changes; no agent's file is written.
            name = seen.connection[0].name if seen.connection is not None else None
            await self._clear_choice(seen.agent.uid)
            return Applied(
                AuditEvent(
                    AuditEventType.PROVIDER_PROJECTION_REPAIRED.value,
                    seen.agent,
                    {**details, "action": "clear_connection", "connection": name},
                )
            )
        if d.op is Op.REMOVE:
            priors = self._projector.deproject_agent(seen.agent)
            event = AuditEvent(
                AuditEventType.PROVIDER_PROJECTION_REPAIRED.value,
                seen.agent,
                {**details, "action": "deproject"},
            )
            return Applied(event, undo=self._restore(priors))
        if seen.connection is None:
            raise LookupError(f"agent {seen.agent.name} runs on no connection")
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


__all__ = ["TARGET", "ClearChoice", "ProviderProjectionTarget"]
