"""Add, edit and remove the command-line tools a person declares by hand (spec
skill-manager "Declare a command-line tool without a skill").

A tool a skill or MCP server requires is not the person's to declare, but its
description is theirs to write: that is the one field ``edit`` changes on a
tool nobody added by hand.

A tool added here needs no skill and no MCP server: it is one entry in the
vault's ``cli-tools`` state document, and it is listed, checked and read like
any other. When a skill also requires the command, the two are one entry;
removing the hand-added declaration then only drops the declaration — the
entry stays for as long as the skill requires it. Every change is audited.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.skill.cli_requirements import CliRequirementService, CliView
from coffer.domain.audit import AuditEventType
from coffer.domain.skill.cli_declared import (
    DESCRIPTION_MAX,
    MAX_DECLARED,
    CliToolExists,
    CliToolInvalid,
    CliToolNotDeclared,
    DeclaredTool,
    clean_login_check,
    clean_min_version,
    clean_text,
    command_name,
    is_path,
)


class DeclaredToolsStore(Protocol):
    def all(self) -> list[DeclaredTool]: ...

    def notes(self) -> dict[str, str]: ...

    def save(
        self, tools: list[DeclaredTool], *, summary: str, actor: str | None = None
    ) -> None: ...

    def set_note(
        self, command: str, text: str | None, *, summary: str, actor: str | None = None
    ) -> None: ...


class CliPathsStore(Protocol):
    def get(self, command: str) -> str | None: ...

    def set(self, command: str, path: str) -> None: ...

    def drop(self, command: str) -> None: ...


class LocatorPort(Protocol):
    def locate(self, command: str) -> str | None: ...

    def version(self, path: str) -> str | None: ...


@dataclass(frozen=True)
class CliPreview:
    """What Coffer found for a name or path, before anything is saved."""

    command: str
    path: str | None
    version: str | None
    #: Already added by hand.
    added: bool
    #: A skill or MCP server already requires it.
    required: bool


class CliToolService:
    def __init__(
        self,
        *,
        requirements: CliRequirementService,
        declared: DeclaredToolsStore,
        paths: CliPathsStore,
        probe: LocatorPort,
        audit: AuditService,
    ) -> None:
        self._requirements = requirements
        self._declared = declared
        self._paths = paths
        self._probe = probe
        self._audit = audit

    async def preview(self, raw: str) -> CliPreview:
        command = command_name(raw)
        path = await asyncio.to_thread(self._probe.locate, raw.strip() if is_path(raw) else command)
        version = await asyncio.to_thread(self._probe.version, path) if path else None
        added = any(t.command == command for t in self._declared.all())
        listing = await self._requirements.listing()
        required = any(
            v.required.command == command
            and (
                v.required.needed_by or v.required.needed_by_servers or v.required.needed_by_coffer
            )
            for v in listing.items
        )
        return CliPreview(command, path, version, added, required)

    async def add(
        self,
        raw: str,
        *,
        title: str | None = None,
        description: str | None = None,
        min_version: str | None = None,
        login_check: str | None = None,
        actor: str = "api",
    ) -> CliView:
        command = command_name(raw)
        tools = self._declared.all()
        if any(t.command == command for t in tools):
            raise CliToolExists(command)
        if len(tools) >= MAX_DECLARED:
            raise CliToolInvalid(f"at most {MAX_DECLARED} command-line tools can be added")
        if is_path(raw) and await asyncio.to_thread(self._probe.locate, raw.strip()) is None:
            raise CliToolInvalid(f"{raw.strip()!r} is not an executable file")
        tool = DeclaredTool(
            command,
            clean_text(title, "title"),
            clean_text(description, "description", DESCRIPTION_MAX),
            clean_min_version(min_version),
            clean_login_check(command, login_check),
        )
        if is_path(raw):
            await asyncio.to_thread(self._paths.set, command, raw.strip())
        await self._save([*tools, tool], f"Added the command-line tool {command}", actor)
        await self._audit.record(
            AuditEventType.CLI_TOOL_ADDED.value, actor=actor, details={"command": command}
        )
        return await self._after(command)

    async def edit(self, command: str, changes: dict[str, Any], *, actor: str = "api") -> CliView:
        """``changes`` holds only the fields the caller sent; ``None`` clears one.
        A tool nobody added by hand takes only ``description``."""
        tools = self._declared.all()
        current = next((t for t in tools if t.command == command), None)
        if current is None:
            if set(changes) - {"description"}:
                raise CliToolNotDeclared(command)
            return await self._describe(command, changes.get("description"), actor)
        edited = replace(current)
        if "title" in changes:
            edited = replace(edited, title=clean_text(changes["title"], "title"))
        if "description" in changes:
            edited = replace(
                edited,
                description=clean_text(changes["description"], "description", DESCRIPTION_MAX),
            )
        if "min_version" in changes:
            edited = replace(edited, min_version=clean_min_version(changes["min_version"]))
        if "login_check" in changes:
            edited = replace(edited, login_check=clean_login_check(command, changes["login_check"]))
        if edited != current:
            rest = [t for t in tools if t.command != command]
            await self._save([*rest, edited], f"Edited the command-line tool {command}", actor)
            await self._audit.record(
                AuditEventType.CLI_TOOL_EDITED.value,
                actor=actor,
                details={"command": command, "fields": sorted(changes)},
            )
        return await self._after(command)

    async def _describe(self, command: str, raw: str | None, actor: str) -> CliView:
        """Keep the description of a tool a skill or MCP server requires."""
        await self._requirements.get(command)  # CliNotKnown for a command nobody lists
        text = clean_text(raw, "description", DESCRIPTION_MAX)
        if self._declared.notes().get(command) != text:
            await asyncio.to_thread(
                self._declared.set_note,
                command,
                text,
                summary=f"Described the command-line tool {command}",
                actor=actor,
            )
            await self._audit.record(
                AuditEventType.CLI_TOOL_EDITED.value,
                actor=actor,
                details={"command": command, "fields": ["description"]},
            )
        return await self._after(command)

    async def remove(self, command: str, *, actor: str = "api") -> None:
        tools = self._declared.all()
        if not any(t.command == command for t in tools):
            raise CliToolNotDeclared(command)
        rest = [t for t in tools if t.command != command]
        await self._save(rest, f"Removed the command-line tool {command}", actor)
        await asyncio.to_thread(self._paths.drop, command)
        self._requirements.forget(command)
        await self._audit.record(
            AuditEventType.CLI_TOOL_REMOVED.value, actor=actor, details={"command": command}
        )

    async def _save(self, tools: list[DeclaredTool], summary: str, actor: str) -> None:
        await asyncio.to_thread(self._declared.save, tools, summary=summary, actor=actor)

    async def _after(self, command: str) -> CliView:
        self._requirements.forget(command)
        return await self._requirements.check(command)


__all__ = ["CliPreview", "CliToolService"]
