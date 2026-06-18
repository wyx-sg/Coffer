"""AgentInstructionsService — master-instructions hub + per-agent delivery.

Spec 004 item 1. A single master-instructions document lives in Coffer's hub
(``~/.coffer/instructions/AGENTS.md``); delivery writes it into an agent's
``instructions`` config file (CLAUDE.md / AGENTS.md / SOUL.md) as a Coffer-managed
block fenced by distinct markers so it coexists with spec 007's memory block.
Adoption goes the other way — an agent's block (or its whole instructions file
when no block is present) becomes the new master.

Every file mutation goes through the shared ``ConfigFileStorePort`` (atomic write
+ ``.bak`` + sha256 fingerprint); the block mechanics are the pure helpers in
``domain/agent/managed_block.py``.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Callable
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, config_files_for
from coffer.domain.agent.instructions import (
    INSTRUCTIONS_BLOCK_END,
    INSTRUCTIONS_BLOCK_START,
    InstructionsDeliveryStatus,
    MasterInstructions,
)
from coffer.domain.agent.managed_block import (
    extract_block,
    has_block,
    strip_block,
    upsert_block,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import InstructionsMasterStale, InstructionsUnsupported

_INSTRUCTIONS_KEY = "instructions"


def default_master_path() -> pathlib.Path:
    """Absolute path of the hub master-instructions document.

    ``$HOME/.coffer/instructions/AGENTS.md`` — the single editable source of
    truth, read from the same ``$HOME`` as the rest of the agent layer so a
    test-overridden home is honoured.
    """
    home = pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))
    return home / ".coffer" / "instructions" / "AGENTS.md"


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


class AgentInstructionsService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
        master_path: Callable[[], pathlib.Path] = default_master_path,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._master_path = master_path

    # --- master instructions --------------------------------------------------

    def get_master(self) -> MasterInstructions:
        """The hub master document (empty content + ``""`` fingerprint when it
        has never been written; the read never creates the file)."""
        raw = self._store.read_text(self._master_path())
        return MasterInstructions(content=raw or "", fingerprint=self._store.fingerprint(raw))

    async def set_master(
        self, content: str, *, expected_fingerprint: str | None = None, actor: str = "api"
    ) -> MasterInstructions:
        """Write the hub master document. When ``expected_fingerprint`` is given
        and no longer matches the stored content, the write is rejected (409)."""
        path = self._master_path()
        if expected_fingerprint is not None:
            current = self._store.read_text(path)
            if self._store.fingerprint(current) != expected_fingerprint:
                raise InstructionsMasterStale()
        self._store.write_text_atomic(path, content)
        await self._audit.record(
            AuditEventType.AGENT_INSTRUCTIONS_MASTER_WRITTEN.value,
            actor=actor,
            details={"path": str(path)},
        )
        return MasterInstructions(content=content, fingerprint=self._store.fingerprint(content))

    # --- per-agent delivery ---------------------------------------------------

    async def _instructions_spec(self, name: str) -> ConfigFileSpec:
        """Resolve the agent's ``instructions`` config-file spec.

        Raises ``ResourceNotFound`` (404) for an unknown agent, and
        ``InstructionsUnsupported`` (422) for a type whose allowlist has no
        instructions file (e.g. ``openclaw``).
        """
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        for spec in config_files_for(cfg.type, cfg.resolved_config_dir()):
            if spec.key == _INSTRUCTIONS_KEY:
                return spec
        raise InstructionsUnsupported(cfg.type.value)

    async def status(self, name: str) -> InstructionsDeliveryStatus:
        """Whether the managed block is delivered and in sync with the master."""
        spec = await self._instructions_spec(name)
        text = self._store.read_text(spec.path) or ""
        body = extract_block(
            text, start_marker=INSTRUCTIONS_BLOCK_START, end_marker=INSTRUCTIONS_BLOCK_END
        )
        master = self.get_master().content
        in_sync = body is not None and body.strip() == master.strip()
        return InstructionsDeliveryStatus(delivered=body is not None, in_sync=in_sync)

    async def deliver(self, name: str, *, actor: str = "api") -> InstructionsDeliveryStatus:
        """Write/refresh the master into the agent's managed instructions block."""
        spec = await self._instructions_spec(name)
        master = self.get_master().content
        text = self._store.read_text(spec.path) or ""
        new_text = upsert_block(
            text, master, start_marker=INSTRUCTIONS_BLOCK_START, end_marker=INSTRUCTIONS_BLOCK_END
        )
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_INSTRUCTIONS_DELIVERED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(spec.path)},
        )
        return InstructionsDeliveryStatus(delivered=True, in_sync=True)

    async def remove(self, name: str, *, actor: str = "api") -> InstructionsDeliveryStatus:
        """Strip only the managed instructions block. No-op success when absent."""
        spec = await self._instructions_spec(name)
        text = self._store.read_text(spec.path)
        if text is None or not has_block(text, start_marker=INSTRUCTIONS_BLOCK_START):
            return InstructionsDeliveryStatus(delivered=False, in_sync=False)
        new_text = strip_block(
            text, start_marker=INSTRUCTIONS_BLOCK_START, end_marker=INSTRUCTIONS_BLOCK_END
        )
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_INSTRUCTIONS_REMOVED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(spec.path)},
        )
        return InstructionsDeliveryStatus(delivered=False, in_sync=False)

    async def adopt(self, name: str, *, actor: str = "api") -> MasterInstructions:
        """Make the agent's instructions the new master.

        Takes the agent's managed-block body, or — when no block is present —
        its whole instructions file. The agent's own file is left untouched.
        """
        spec = await self._instructions_spec(name)
        text = self._store.read_text(spec.path) or ""
        body = extract_block(
            text, start_marker=INSTRUCTIONS_BLOCK_START, end_marker=INSTRUCTIONS_BLOCK_END
        )
        content = body if body is not None else text
        path = self._master_path()
        self._store.write_text_atomic(path, content)
        await self._audit.record(
            AuditEventType.AGENT_INSTRUCTIONS_ADOPTED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(path), "source": str(spec.path)},
        )
        return MasterInstructions(content=content, fingerprint=self._store.fingerprint(content))
