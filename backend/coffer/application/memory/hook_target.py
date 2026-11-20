"""Coffer's session-start hook in each agent, as a reconcile target (spec
memory "Hand a session its project's memories at start"; ADR
one-level-triggered-reconciler-compares-parameters).

While the memory feature is on, every registered agent whose record names a
place for it (:class:`~coffer.domain.agent.session_hook.SessionHookSpec`)
carries exactly one hook of Coffer's: ``<coffer> memory session-start`` under
its ``SessionStart`` event. While the feature is off, or once the agent is
unregistered from Coffer, the hook is removed. A hook is Coffer's when its
command runs ``memory session-start``; every other hook and every other key in
the file is left byte-for-byte as it was parsed and rewritten.

Codex runs a new or changed hook only after the person reviews it once
(``/hooks`` in the CLI, Settings > Hooks in the app); Coffer cannot and does
not approve it on their behalf. The command does not change between passes, so
one review lasts until the CLI moves.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.session_hook import HOOK_SUBCOMMAND, SessionHookSpec
from coffer.domain.agent.types import agent_display_name
from coffer.domain.audit import AuditEventType
from coffer.domain.reconcile import (
    Decision,
    Difference,
    Disposition,
    Item,
    Op,
    PlannedChange,
    Subject,
)
from coffer.domain.resource import Resource

_log = logging.getLogger(__name__)

TARGET = "memory_hook"


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
    agent: Resource
    path: pathlib.Path
    spec: SessionHookSpec


def hook_command(cli: str) -> str:
    """The command Coffer's hook runs."""
    return " ".join([shlex.quote(cli), *HOOK_SUBCOMMAND])


def is_ours(command: object) -> bool:
    """Whether a hook command is Coffer's session-start hook."""
    if not isinstance(command, str):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    return any(
        tuple(words[i : i + len(HOOK_SUBCOMMAND)]) == HOOK_SUBCOMMAND
        for i in range(1, max(1, len(words) - len(HOOK_SUBCOMMAND) + 1))
    )


def _groups(doc: dict[str, Any], event: str) -> list[Any]:
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return []
    groups = hooks.get(event)
    return groups if isinstance(groups, list) else []


def installed_commands(text: str | None, event: str) -> list[str]:
    """Every command of Coffer's hook in a hooks file (normally one)."""
    if not text or not text.strip():
        return []
    doc = json.loads(text)
    if not isinstance(doc, dict):
        return []
    found: list[str] = []
    for group in _groups(doc, event):
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        for hook in group["hooks"]:
            if isinstance(hook, dict) and is_ours(hook.get("command")):
                found.append(hook["command"])
    return found


def apply_hook(text: str | None, event: str, command: str | None) -> str:
    """``text`` with Coffer's hook set to ``command``, or removed when
    ``command`` is ``None``. Every other hook and key is kept."""
    doc: dict[str, Any] = json.loads(text) if text and text.strip() else {}
    if not isinstance(doc, dict):
        raise ValueError("the hooks file is not a JSON object")
    kept: list[Any] = []
    for group in _groups(doc, event):
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            others = [
                h for h in group["hooks"] if not (isinstance(h, dict) and is_ours(h.get("command")))
            ]
            if not others and group["hooks"]:
                continue
            group = {**group, "hooks": others}
        kept.append(group)
    if command is not None:
        kept.append({"hooks": [{"type": "command", "command": command}]})
    current = doc.get("hooks")
    hooks: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)
    if hooks:
        doc["hooks"] = hooks
    else:
        doc.pop("hooks", None)
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def strip_hook(store: _Store, agent: Resource) -> bool:
    """Take Coffer's hook out of one agent's hooks file, leaving every other
    hook; whether there was one. The uninstall runs it (spec daemon "Uninstall
    Coffer from this machine"), after which no reconcile pass puts it back."""
    cfg = AgentConfig.model_validate(agent.config)
    hook = descriptor_for(cfg.type).session_hook
    if hook is None:
        return False
    path = spec_for(cfg.type, hook.config_key, cfg.resolved_config_dir()).path
    before = store.read_text(path)
    if not installed_commands(before, hook.event):
        return False
    store.write_text_atomic(
        path,
        apply_hook(before, hook.event, None),
        expected_fingerprint=store.fingerprint(before),
    )
    return True


class MemoryHookTarget:
    """Implements ``ReconcileTarget`` for Coffer's session-start hook."""

    name = TARGET
    kinds = frozenset({"agent"})

    def __init__(
        self,
        *,
        agents: _Agents,
        store: _Store,
        cli_resolver: Callable[[], str],
        enabled: Callable[[], bool],
    ) -> None:
        self._agents = agents
        self._store = store
        self._cli = cli_resolver
        self._enabled = enabled

    async def _homes(self) -> dict[str, _Home]:
        homes: dict[str, _Home] = {}
        seen: set[pathlib.Path] = set()
        for row in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(row.config)
            except Exception:
                continue
            hook = descriptor_for(cfg.type).session_hook
            if hook is None:
                continue
            path = spec_for(cfg.type, hook.config_key, cfg.resolved_config_dir()).path
            if path in seen:
                continue
            seen.add(path)
            homes[row.uid] = _Home(row, path, hook)
        return homes

    def _item(self, uid: str, home: _Home, command: str) -> Item:
        return Item(
            key=uid,
            subject=Subject("agent", uid, agent_display_name(home.agent.config, home.agent.name)),
            params={"command": command},
            file=str(home.path),
            text=command,
        )

    async def desired(self) -> Sequence[Item]:
        if not self._enabled():
            return []
        command = hook_command(self._cli())
        return [self._item(uid, home, command) for uid, home in (await self._homes()).items()]

    async def observe(self) -> Sequence[Item]:
        homes = await self._homes()

        def _scan() -> list[Item]:
            items: list[Item] = []
            for uid, home in homes.items():
                try:
                    found = installed_commands(self._store.read_text(home.path), home.spec.event)
                except ValueError:
                    _log.warning("memory_hook: %s does not parse; left alone", home.path)
                    continue
                if found:
                    items.append(self._item(uid, home, found[0] if len(found) == 1 else "*"))
            return items

        return await asyncio.to_thread(_scan)

    def decide(self, differences: Sequence[Difference], trigger: object) -> Sequence[Decision]:
        reasons = {
            Op.ADD: ("missing_hook", "Coffer's session-start hook is not installed."),
            Op.MODIFY: ("stale_hook", "The installed hook runs another command."),
            Op.REMOVE: ("unwanted_hook", "Memory is off, so the hook should not be there."),
        }
        return [Decision(Disposition.REPAIR, *reasons[d.op]) for d in differences]

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        home = (await self._homes()).get(d.key)
        if home is None:
            raise LookupError(f"agent {d.key} is no longer registered")
        command = d.desired.params["command"] if d.desired is not None else None
        before = self._store.read_text(home.path)
        new = apply_hook(before, home.spec.event, command)
        self._store.write_text_atomic(
            home.path, new, expected_fingerprint=self._store.fingerprint(before)
        )
        event = (
            AuditEventType.MEMORY_HOOK_INSTALLED
            if command is not None
            else AuditEventType.MEMORY_HOOK_REMOVED
        )
        return Applied(
            AuditEvent(event.value, home.agent, {"path": str(home.path), "command": command}),
            undo=self._restore(home.path, before),
        )

    def _restore(self, path: pathlib.Path, before: str | None) -> Undo:
        async def _undo() -> None:
            if before is None:
                self._store.delete_with_backup(path)
            else:
                self._store.write_text_atomic(path, before)

        return _undo


__all__ = [
    "TARGET",
    "MemoryHookTarget",
    "apply_hook",
    "hook_command",
    "installed_commands",
    "is_ours",
    "strip_hook",
]
