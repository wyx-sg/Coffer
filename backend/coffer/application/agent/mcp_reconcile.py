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
connected exactly when an entry for it exists somewhere Coffer looks — its own
file, or another agent's file that still holds an entry carrying its uid — and
the target never adds an entry to an agent that holds none.

**Where an entry belongs.** Each agent's own MCP file, which for Claude Code
with a custom config directory is ``<dir>/.claude.json``. An entry an older
Coffer wrote into the standard ``~/.claude.json`` for a custom-directory agent
(it carries that agent's uid) is *misplaced*: the pass installs it into the
agent's own file first and removes it from the other file second, so a
failure between the two leaves the entry in both places rather than neither.
Entries naming no registered agent, and every entry that is not Coffer's, are
never touched.

**Direction policy.** A stale entry is repaired; a misplaced one is moved.
When the shim cannot be found there is nothing correct to write: the item is
*blocked* (``missing_launcher``) and reported until the launcher is back.
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileFormat, spec_for
from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS, descriptor_for
from coffer.domain.agent.mcp_injection import McpInjectionSpec
from coffer.domain.agent.mcp_install import (
    apply_install,
    apply_uninstall,
    desired_entry,
    installed_entry,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileFormatInvalid, ShimNotFound
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


@dataclass(frozen=True)
class _Found:
    """A coffer entry found in one file."""

    path: pathlib.Path
    owner: str | None  # the --agent-uid it carries
    params: dict[str, object]


def _title(r: Resource) -> str:
    return r.title or r.name


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

    def _candidate_files(
        self, homes: dict[str, _Home]
    ) -> dict[pathlib.Path, tuple[ConfigFileFormat, McpInjectionSpec]]:
        """Every file an entry may sit in: each agent's own, plus each type's
        standard file (where older builds wrote every agent's entry)."""
        files = {h.path: (h.fmt, h.injection) for h in homes.values()}
        for d in AGENT_DESCRIPTORS.values():
            if d.mcp is None:
                continue
            spec = spec_for(d.type, d.mcp.config_key, d.default_config_dir())
            files.setdefault(spec.path, (spec.format, d.mcp))
        return files

    def _scan(self, homes: dict[str, _Home]) -> list[_Found]:
        found: list[_Found] = []
        for path, (fmt, inj) in self._candidate_files(homes).items():
            text = self._store.read_text(path)
            if not text:
                continue
            try:
                params = installed_entry(fmt, text, container_key=inj.container_key)
            except ConfigFileFormatInvalid:
                _log.warning("mcp_entry: %s does not parse; left alone", path)
                continue
            if params is None:
                continue
            args = list(params.get("args") or [])
            owner = next((v for f, v in pairwise(args) if f == "--agent-uid"), None)
            found.append(_Found(path, owner, params))
        return found

    @staticmethod
    def _key(found: _Found, homes: dict[str, _Home]) -> str | None:
        """The key an entry is judged under: the agent whose own file holds
        it, unless it carries another registered agent's uid and that agent's
        own file is elsewhere (misplaced). ``None``: nobody's to judge."""
        home_of_file = next((u for u, h in homes.items() if h.path == found.path), None)
        owner = found.owner
        if owner is not None and owner in homes and homes[owner].path != found.path:
            return f"{owner}@{found.path}"
        return home_of_file

    def _shim(self) -> str | None:
        try:
            return self._resolve_shim()
        except ShimNotFound:
            return None

    # --- the target ------------------------------------------------------------

    async def desired(self) -> Sequence[Item]:
        homes = await self._homes()
        wanted: set[str] = set()
        for found in self._scan(homes):
            key = self._key(found, homes)
            if key is None:
                continue
            wanted.add(key.split("@", 1)[0])
        shim = self._shim()
        items: list[Item] = []
        for uid, home in homes.items():
            if uid not in wanted:
                continue
            params = desired_entry(shim, uid)
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
        for found in self._scan(homes):
            key = self._key(found, homes)
            if key is None:
                continue
            uid = key.split("@", 1)[0]
            items.append(
                Item(
                    key=key,
                    subject=Subject("agent", uid, _title(homes[uid].agent)),
                    params=found.params,
                    file=str(found.path),
                    text=_text(found.params),
                )
            )
        return items

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        blocked_adds = {
            d.key
            for d in differences
            if d.op is not Op.REMOVE and d.desired is not None and not d.desired.params["command"]
        }
        out: list[Decision] = []
        for d in differences:
            uid = d.key.split("@", 1)[0]
            if d.key in blocked_adds or (d.op is Op.REMOVE and uid in blocked_adds):
                out.append(
                    Decision(
                        Disposition.BLOCKED,
                        "missing_launcher",
                        "The coffer-mcp-shim launcher cannot be found, so there is no "
                        "correct entry to write.",
                    )
                )
            elif d.op is Op.REMOVE:
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "misplaced_entry",
                        f"The entry for this agent sits in {d.file}, which the agent "
                        "does not read; it is moved to the agent's own file.",
                    )
                )
            elif d.op is Op.ADD:
                out.append(
                    Decision(
                        Disposition.REPAIR,
                        "misplaced_entry",
                        "The agent's entry is in a file the agent does not read; it is "
                        "installed into the agent's own file.",
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
        uid = d.key.split("@", 1)[0]
        home = homes.get(uid)
        if home is None:
            raise LookupError(f"agent {uid} is no longer registered")
        if d.op is Op.REMOVE:
            assert d.observed is not None and d.observed.file is not None
            path = pathlib.Path(d.observed.file)
            # Install first, remove second: the entry leaves the wrong file only
            # once the agent's own file carries the current one.
            own = self._store.read_text(home.path) or ""
            inj = home.injection
            if installed_entry(home.fmt, own, container_key=inj.container_key) != desired_entry(
                self._shim(), uid
            ):
                raise RuntimeError(f"{home.path} does not hold the agent's entry yet; not moved")
            before = self._store.read_text(path)
            if before is None:
                raise FileNotFoundError(str(path))
            new = apply_uninstall(home.fmt, before, container_key=home.injection.container_key)
            self._store.write_text_atomic(
                path, new, expected_fingerprint=self._store.fingerprint(before)
            )
            return Applied(
                AuditEvent(
                    AuditEventType.AGENT_MCP_UNINSTALLED.value,
                    home.agent,
                    {"path": str(path), "moved_to": str(home.path)},
                ),
                undo=self._restore(path, before),
            )
        shim = self._resolve_shim()  # ShimNotFound fails the item before any write
        before = self._store.read_text(home.path)
        new = apply_install(
            home.fmt,
            before or "",
            shim,
            container_key=home.injection.container_key,
            entry_style=home.injection.entry_style,
            agent_uid=uid,
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
