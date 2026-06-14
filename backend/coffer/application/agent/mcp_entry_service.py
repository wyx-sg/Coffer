"""AgentMcpEntryService — list / remove / toggle / adopt MCP entries in an agent's own config files.

Operates on the MCP-bearing subset of the per-type config-file allowlist
(``_MCP_SOURCE_KEYS``) using the pure text transforms in
``domain/agent/mcp_entries.py``. Coffer's own gateway entry (``coffer``) is
protected — it is managed exclusively by the install/uninstall flow in
``mcp_service.py``.

``adopt`` promotes an agent-config entry into a registered Coffer
``mcp_server`` resource: secret-looking env/header keys MUST be mapped to
keychain refs (values go into the OS keychain, never the config DB), the
resource is registered and verified FIRST, and only then is the source entry
removed from the agent's file — any failure after registration rolls the
resource back so the user never loses a working entry.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_entries import (
    COFFER_SERVER_KEY,
    McpEntry,
    parse_entries,
    secret_env_keys,
    to_transport_config,
)
from coffer.domain.agent.mcp_entries import (
    remove_entry as remove_entry_text,
)
from coffer.domain.agent.mcp_entries import (
    set_entry_enabled as set_entry_enabled_text,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileNotAllowed
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import (
    AdoptSecretUnresolved,
    AgentConfigParseError,
    McpEntryNotFound,
    McpEntryProtected,
    McpEntrySourceAmbiguous,
    McpEntryToggleUnsupported,
)


def _source_keys(agent_type: AgentType) -> tuple[str, ...]:
    """Allowlisted config-file keys that hold the agent's MCP servers."""
    return descriptor_for(agent_type).resolved_mcp_source_keys()


def _container_key(agent_type: AgentType) -> str | None:
    """Top-level MCP container key for the agent (None → format default)."""
    inj = descriptor_for(agent_type).mcp
    return inj.container_key if inj else None


@dataclass(frozen=True)
class ParseErrorInfo:
    """One config file that could not be parsed while listing MCP entries."""

    source: str
    path: str
    error: str


@dataclass(frozen=True)
class McpEntriesView:
    """Merged MCP entries across an agent's config files + parse-error state."""

    items: list[McpEntry]
    parse_errors: list[ParseErrorInfo]


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


class _ResourcePort(Protocol):
    """Minimal structural slice of ``ResourceService`` used by adopt/list."""

    async def register(
        self,
        kind: str,
        name: str,
        config: dict[str, Any],
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource: ...

    async def get(self, ref: ResourceRef) -> Resource: ...

    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]: ...

    async def delete(self, ref: ResourceRef, actor: str) -> None: ...


class _CredentialStorePort(Protocol):
    """Write-only slice of the credential store (secrets flow IN, never out)."""

    def set(self, ref: str, value: str) -> None: ...

    def delete(self, ref: str) -> None: ...


def _matches_transport(entry: McpEntry, transport: Mapping[str, Any]) -> bool:
    """Equivalence between a config-file entry and a registered resource's transport.

    stdio: same command AND same args; http: same url. Tolerates missing keys.
    """
    if entry.transport == "stdio":
        raw_args = transport.get("args") or []
        args = [str(a) for a in raw_args] if isinstance(raw_args, (list, tuple)) else []
        return (
            transport.get("type") == "stdio"
            and transport.get("command") == entry.command
            and args == list(entry.args)
        )
    return transport.get("type") == "http" and transport.get("url") == entry.url


class AgentMcpEntryService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
        resource_service: _ResourcePort,
        credentials: _CredentialStorePort,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._rs = resource_service
        self._credentials = credentials

    async def _config_for(self, name: str) -> AgentConfig:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        resource = await self._agents.get(name)
        return AgentConfig.model_validate(resource.config)

    def _source_specs(self, cfg: AgentConfig) -> list[ConfigFileSpec]:
        cfg_dir = cfg.resolved_config_dir()
        return [spec_for(cfg.type, key, cfg_dir) for key in _source_keys(cfg.type)]

    async def list_entries(self, name: str) -> McpEntriesView:
        """Merged MCP entries across all MCP-bearing config files.

        Missing files are skipped; unparseable files degrade to an explicit
        ``ParseErrorInfo`` instead of failing the whole view (spec 004 FR-030).
        Entries (except Coffer's own) are annotated with the name of an
        equivalent registered ``mcp_server`` resource, if any.
        """
        cfg = await self._config_for(name)
        items: list[McpEntry] = []
        parse_errors: list[ParseErrorInfo] = []
        for spec in self._source_specs(cfg):
            text = self._store.read_text(spec.path)
            if text is None:
                continue
            try:
                items.extend(
                    parse_entries(
                        spec.format, text, source=spec.key, container_key=_container_key(cfg.type)
                    )
                )
            except AgentConfigParseError as e:
                parse_errors.append(
                    ParseErrorInfo(source=spec.key, path=str(spec.path), error=str(e))
                )

        resources = await self._rs.list(kind="mcp_server")
        annotated: list[McpEntry] = []
        for entry in items:
            match: str | None = None
            if not entry.is_coffer:
                for r in resources:
                    transport = r.config.get("transport")
                    if isinstance(transport, Mapping) and _matches_transport(entry, transport):
                        match = r.name
                        break
            annotated.append(dataclasses.replace(entry, matches_resource=match) if match else entry)
        return McpEntriesView(items=annotated, parse_errors=parse_errors)

    async def _locate(
        self, name: str, entry: str, source: str | None
    ) -> tuple[ConfigFileSpec, str, McpEntry]:
        """Find the single source file containing ``entry``.

        Returns ``(spec, text, parsed_entry)``. Protected/ambiguity/404 rules:
        the ``coffer`` entry is never addressable; with ``source=None`` an
        entry present in multiple files raises ``McpEntrySourceAmbiguous``;
        zero hits raise ``McpEntryNotFound`` — unless a source failed parsing,
        in which case the parse error surfaces so the caller isn't misled.
        """
        if entry == COFFER_SERVER_KEY:
            raise McpEntryProtected(entry)
        cfg = await self._config_for(name)
        specs = self._source_specs(cfg)
        if source is not None:
            if source not in _source_keys(cfg.type):
                raise ConfigFileNotAllowed(cfg.type.value, source)
            specs = [s for s in specs if s.key == source]

        hits: list[tuple[ConfigFileSpec, str, McpEntry]] = []
        first_parse_error: AgentConfigParseError | None = None
        for spec in specs:
            text = self._store.read_text(spec.path)
            if text is None:
                continue
            try:
                parsed = parse_entries(
                    spec.format, text, source=spec.key, container_key=_container_key(cfg.type)
                )
            except AgentConfigParseError as e:
                if first_parse_error is None:
                    first_parse_error = e
                continue
            for p in parsed:
                if p.name == entry:
                    hits.append((spec, text, p))
                    break
        if not hits:
            if first_parse_error is not None:
                raise first_parse_error
            raise McpEntryNotFound(entry)
        if len(hits) > 1:
            raise McpEntrySourceAmbiguous(entry)
        return hits[0]

    async def remove_entry(
        self, name: str, entry: str, *, source: str | None = None, actor: str = "api"
    ) -> None:
        """Remove ``entry`` from the agent config file that contains it."""
        cfg = await self._config_for(name)
        spec, text, _parsed = await self._locate(name, entry, source)
        new_text = remove_entry_text(
            spec.format, text, entry, container_key=_container_key(cfg.type)
        )
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_MCP_ENTRY_REMOVED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"entry": entry, "source": spec.key},
        )

    async def set_enabled(
        self, name: str, entry: str, enabled: bool, *, actor: str = "api"
    ) -> None:
        """Set the per-entry ``enabled`` flag (Codex TOML only)."""
        cfg = await self._config_for(name)
        if cfg.type is not AgentType.CODEX:
            raise McpEntryToggleUnsupported(cfg.type.value)
        if entry == COFFER_SERVER_KEY:
            raise McpEntryProtected(entry)
        spec = spec_for(cfg.type, _source_keys(cfg.type)[0], cfg.resolved_config_dir())
        text = self._store.read_text(spec.path)
        if text is None:
            raise McpEntryNotFound(entry)
        new_text = set_entry_enabled_text(text, entry, enabled)
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"key": spec.key, "entry": entry, "enabled": enabled},
        )

    async def _cleanup_refs(self, refs: dict[str, str]) -> None:
        """Best-effort removal of keychain entries written by a failed adopt."""
        import contextlib

        def _delete_all() -> None:
            for ref in refs.values():
                with contextlib.suppress(Exception):
                    self._credentials.delete(ref)

        # One to_thread for the whole rollback: the store write blocks on
        # SQLite's busy_timeout, which on the loop would freeze the very
        # coroutine holding the write lock (guaranteed deadlock) — and a
        # single thread, once started, runs to completion even if the
        # awaiting task is cancelled, so the rollback stays atomic.
        await asyncio.to_thread(_delete_all)

    async def adopt(
        self,
        name: str,
        entry: str,
        *,
        source: str | None = None,
        new_name: str | None = None,
        secrets: dict[str, str] | None = None,
        actor: str = "api",
    ) -> Resource:
        """Promote a config-file entry into a registered ``mcp_server`` resource.

        ``secrets`` maps secret-looking env/header KEY names to credential refs;
        every flagged key must be mapped (``AdoptSecretUnresolved`` otherwise).
        Secret VALUES go straight into the credential store and into
        ``credential_refs`` — never into the resource config, audit log, or
        any log line. Register + verify happen BEFORE the source entry is
        removed; a failure after registration deletes the new resource so the
        agent's file is never left without a working entry.
        """
        cfg = await self._config_for(name)
        spec, _text, parsed_entry = await self._locate(name, entry, source)

        flagged = secret_env_keys({**parsed_entry.env, **parsed_entry.headers})
        unresolved = [k for k in flagged if k not in (secrets or {})]
        if unresolved:
            raise AdoptSecretUnresolved(unresolved)

        # Narrow the caller-supplied mapping to keys that actually appear in the
        # entry's env or headers.  A key absent from both would still end up in
        # credential_refs (via to_transport_config) while the stored secret it
        # references was never written — dangling reference.
        provided = secrets or {}
        applicable = {
            k: r for k, r in provided.items() if k in parsed_entry.env or k in parsed_entry.headers
        }

        def _write_secrets() -> None:
            import contextlib

            written: list[str] = []
            try:
                for key, ref in applicable.items():
                    env, headers = parsed_entry.env, parsed_entry.headers
                    value = env[key] if key in env else headers[key]
                    self._credentials.set(ref, value)
                    written.append(ref)
            except Exception:
                # Don't orphan the refs already written before the failure.
                for ref in written:
                    with contextlib.suppress(Exception):
                        self._credentials.delete(ref)
                raise

        # One to_thread for all writes: off the loop (SQLite busy-wait would
        # deadlock against the loop's own writer) and atomic under task
        # cancellation — the thread runs to completion once started.
        await asyncio.to_thread(_write_secrets)

        config = {"transport": to_transport_config(parsed_entry, applicable)}
        try:
            # ResourceAlreadyExists bubbles — the route adds a rename suggestion.
            resource = await self._rs.register(
                kind="mcp_server", name=new_name or entry, config=config, actor=actor
            )
        except Exception:
            await self._cleanup_refs(applicable)  # don't orphan just-written secrets
            raise
        try:
            # Verify the resource is really readable before touching the file.
            await self._rs.get(ResourceRef("mcp_server", resource.name))
            # Re-read the file immediately before the write to avoid a TOCTOU
            # window: another writer may have modified the file between _locate
            # and here (two awaits above).
            current = self._store.read_text(spec.path) or ""
            try:
                new_text = remove_entry_text(
                    spec.format, current, entry, container_key=_container_key(cfg.type)
                )
            except McpEntryNotFound:
                new_text = None  # entry vanished concurrently — nothing to remove
            if new_text is not None:
                self._store.write_text_atomic(spec.path, new_text)
        except Exception:
            # Roll back: never leave both a half-adopted resource AND a
            # still-present (or half-removed) config entry inconsistent.
            await self._rs.delete(ResourceRef("mcp_server", resource.name), actor=actor)
            await self._cleanup_refs(applicable)
            raise
        await self._audit.record(
            AuditEventType.AGENT_MCP_ENTRY_ADOPTED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"entry": entry, "resource": resource.name, "source": spec.key},
        )
        return resource
