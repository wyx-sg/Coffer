"""Coffer's own MCP entry, as a reconcile target.

ADR one-level-triggered-reconciler-compares-parameters. The ``coffer`` entry in
an agent's MCP config (``.claude.json`` / ``config.toml``) is judged by every
parameter it carries — the shim path and the ``--agent-uid`` — against what an
install would write now. Before this, status matched the key alone, so a shim
an upgrade moved or an entry naming another agent read as "installed": the
same failure PR #413 found in the delivery hook.

**What is wanted.** Whether an agent is connected is the user's act
(connect / disconnect, spec agent-registry "Connect an agent to Coffer in one
action"), and the entry itself is the record of it. So an agent is wanted
connected exactly when its own MCP file (for Claude Code with a custom config
directory, ``<dir>/.claude.json``) holds a ``coffer`` entry, and the target
never adds an entry to an agent that holds none. Every entry that is not
Coffer's is never touched.

**Direction policy.** A stale entry is repaired. When the shim cannot be found
there is nothing correct to write: the item is *blocked* (``missing_launcher``)
and reported until the launcher is back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileFormat, spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_injection import McpInjectionSpec
from coffer.domain.agent.mcp_install import (
    apply_install,
    desired_entry,
    installed_entry,
)
from coffer.domain.agent.types import agent_display_name
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileFormatInvalid, ShimNotFound
from coffer.domain.reconcile import (
    Decision,
    Difference,
    Disposition,
    Item,
    PlannedChange,
    Subject,
    Trigger,
)
from coffer.domain.resource import Resource

_log = logging.getLogger(__name__)

TARGET = "mcp_entry"


class _Agents(Protocol):
    async def list(self) -> list[Resource]: ...


class _Store(Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(
        self, path: pathlib.Path, text: str, *, expected_fingerprint: str | None = None
    ) -> None: ...
    def fingerprint(self, text: str | None) -> str: ...
    def delete_with_backup(self, path: pathlib.Path) -> bool: ...


@dataclass(frozen=True)
class _Home:
    """One registered agent's own MCP file."""

    agent: Resource
    path: pathlib.Path
    fmt: ConfigFileFormat
    injection: McpInjectionSpec


def _title(r: Resource) -> str:
    return agent_display_name(r.config, r.name)


def _text(params: object) -> str:
    return json.dumps(params, indent=2, sort_keys=True)


class McpEntryTarget:
    """Implements ``ReconcileTarget`` for the ``coffer`` MCP entry."""

    name = TARGET
    kinds = frozenset({"agent"})

    def __init__(self, *, agents: _Agents, store: _Store, shim_resolver: Callable[[], str]) -> None:
        self._agents = agents
        self._store = store
        self._resolve_shim = shim_resolver

    # --- reading ---------------------------------------------------------------

    async def _homes(self) -> dict[str, _Home]:
        homes: dict[str, _Home] = {}
        for row in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(row.config)
            except Exception:
                continue
            injection = descriptor_for(cfg.type).mcp
            if injection is None:
                continue
            spec = spec_for(cfg.type, injection.config_key, cfg.resolved_config_dir())
            homes[row.uid] = _Home(row, spec.path, spec.format, injection)
        return homes

    def _scan(self, homes: dict[str, _Home]) -> dict[str, dict[str, object]]:
        """The installed coffer entry of each agent whose own file holds one,
        by agent uid. A file two agents share is judged under the first."""
        found: dict[str, dict[str, object]] = {}
        seen: set[pathlib.Path] = set()
        for uid, home in homes.items():
            if home.path in seen:
                continue
            seen.add(home.path)
            text = self._store.read_text(home.path)
            if not text:
                continue
            try:
                params = installed_entry(
                    home.fmt,
                    text,
                    container_key=home.injection.container_key,
                    extra_keys=[k for k, _ in home.injection.entry_extras],
                )
            except ConfigFileFormatInvalid:
                _log.warning("mcp_entry: %s does not parse; left alone", home.path)
                continue
            if params is not None:
                found[uid] = params
        return found

    def _shim(self) -> str | None:
        try:
            return self._resolve_shim()
        except ShimNotFound:
            return None

    # --- the target ------------------------------------------------------------

    async def desired(self) -> Sequence[Item]:
        homes = await self._homes()
        wanted = await asyncio.to_thread(self._scan, homes)
        shim = self._shim()
        items: list[Item] = []
        for uid, home in homes.items():
            if uid not in wanted:
                continue
            params = desired_entry(shim, uid, home.injection.entry_extras)
            items.append(
                Item(
                    key=uid,
                    subject=Subject("agent", uid, _title(home.agent)),
                    params=params,
                    file=str(home.path),
                    text=_text(params),
                )
            )
        return items

    async def observe(self) -> Sequence[Item]:
        homes = await self._homes()
        items: list[Item] = []
        for uid, params in (await asyncio.to_thread(self._scan, homes)).items():
            home = homes[uid]
            items.append(
                Item(
                    key=uid,
                    subject=Subject("agent", uid, _title(home.agent)),
                    params=params,
                    file=str(home.path),
                    text=_text(params),
                )
            )
        return items

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        out: list[Decision] = []
        for d in differences:
            if d.desired is not None and not d.desired.params["command"]:
                out.append(
                    Decision(
                        Disposition.BLOCKED,
                        "missing_launcher",
                        "The coffer-mcp-shim launcher cannot be found, so there is no "
                        "correct entry to write.",
                    )
                )
            else:
                names = ", ".join(d.changed_params)
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "stale_entry",
                        f"The installed entry's {names} differ from what Coffer would write now.",
                    )
                )
        return out

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        homes = await self._homes()
        uid = d.key
        home = homes.get(uid)
        if home is None:
            raise LookupError(f"agent {uid} is no longer registered")
        shim = self._resolve_shim()  # ShimNotFound fails the item before any write
        before = self._store.read_text(home.path)
        new = apply_install(
            home.fmt,
            before or "",
            shim,
            container_key=home.injection.container_key,
            entry_style=home.injection.entry_style,
            agent_uid=uid,
            extras=home.injection.entry_extras,
        )
        self._store.write_text_atomic(
            home.path, new, expected_fingerprint=self._store.fingerprint(before)
        )
        return Applied(
            AuditEvent(
                AuditEventType.AGENT_MCP_INSTALLED.value,
                home.agent,
                {"command": shim, "path": str(home.path), "repaired": list(d.changed_params)},
            ),
            undo=self._restore(home.path, before),
        )

    def _restore(self, path: pathlib.Path, before: str | None) -> Undo:
        """Put back what the write replaced (the content its ``.bak`` holds),
        or remove a file the write created."""

        async def _undo() -> None:
            if before is None:
                self._store.delete_with_backup(path)
            else:
                self._store.write_text_atomic(path, before)

        return _undo


__all__ = ["TARGET", "McpEntryTarget"]
