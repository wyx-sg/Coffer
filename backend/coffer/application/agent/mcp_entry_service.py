"""AgentMcpEntryService — list and adopt MCP entries in an agent's own config files.

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

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.mcp_adopt_secrets import (
    SecretStorePort,
    drop_new_refs,
    write_new_refs,
)
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_entries import (
    COFFER_SERVER_KEY,
    McpEntry,
    matches_transport,
    parse_entries,
    secret_env_keys,
    to_transport_config,
)
from coffer.domain.agent.mcp_entries import (
    remove_entry as remove_entry_text,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileNotAllowed, ResourceAlreadyExists
from coffer.domain.resource import Resource
from coffer.domain.secrets import mint_secret_name, secret_ref
from coffer.domain.workspace_errors import (
    AdoptSecretUnresolved,
    AgentConfigParseError,
    McpEntryNotFound,
    McpEntryProtected,
    McpEntrySourceAmbiguous,
)


def _source_keys(agent_type: AgentType) -> tuple[str, ...]:
    """Allowlisted config-file keys that hold the agent's MCP servers."""
    return descriptor_for(agent_type).resolved_mcp_source_keys()


def container_key(agent_type: AgentType) -> str | None:
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


@dataclass(frozen=True)
class McpEntryDetail:
    """One MCP entry and the absolute path of the config file it lives in."""

    entry: McpEntry
    path: str


class _AgentLookup(Protocol):
    async def get(self, uid: str) -> Resource: ...


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

    async def get(self, uid: str) -> Resource: ...

    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]: ...

    async def delete(self, uid: str, actor: str) -> None: ...


class AgentMcpEntryService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
        resource_service: _ResourcePort,
        secrets: SecretStorePort,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._rs = resource_service
        self._secrets = secrets

    async def agent(self, uid: str) -> tuple[Resource, AgentConfig]:
        """The agent row and its parsed config.

        Both halves, because the write paths audit against the resource itself
        — ``AuditService.record`` takes the row, not an identifier it would
        have to resolve again.

        Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        """
        resource = await self._agents.get(uid)
        return resource, AgentConfig.model_validate(resource.config)

    async def _config_for(self, uid: str) -> AgentConfig:
        return (await self.agent(uid))[1]

    def source_specs(self, cfg: AgentConfig) -> list[ConfigFileSpec]:
        cfg_dir = cfg.resolved_config_dir()
        return [spec_for(cfg.type, key, cfg_dir) for key in _source_keys(cfg.type)]

    async def list_entries(self, uid: str) -> McpEntriesView:
        """Merged MCP entries across all MCP-bearing config files.

        Missing files are skipped; unparseable files degrade to an explicit
        ``ParseErrorInfo`` instead of failing the whole view (spec agent-registry
        "Degrade a facet to a parse-error state when its config file is unparseable").
        Entries (except Coffer's own) are annotated with the name of an equivalent
        registered ``mcp_server`` resource, if any.
        """
        cfg = await self._config_for(uid)
        items: list[McpEntry] = []
        parse_errors: list[ParseErrorInfo] = []
        for spec in self.source_specs(cfg):
            text = self._store.read_text(spec.path)
            if text is None:
                continue
            try:
                ck = container_key(cfg.type)
                items.extend(parse_entries(spec.format, text, source=spec.key, container_key=ck))
            except AgentConfigParseError as e:
                parse_errors.append(
                    ParseErrorInfo(source=spec.key, path=str(spec.path), error=str(e))
                )

        return McpEntriesView(items=await self._annotate(items), parse_errors=parse_errors)

    async def _annotate(self, items: list[McpEntry]) -> list[McpEntry]:
        """Fill ``matches_resource`` with an equivalent registered server's name."""
        registered = [
            (r.name, t)
            for r in await self._rs.list(kind="mcp_server")
            if isinstance(t := r.config.get("transport"), Mapping)
        ]
        out: list[McpEntry] = []
        for entry in items:
            match = None
            if not entry.is_coffer:
                match = next((n for n, t in registered if matches_transport(entry, t)), None)
            out.append(dataclasses.replace(entry, matches_resource=match) if match else entry)
        return out

    async def get_entry(self, uid: str, entry: str, *, source: str | None = None) -> McpEntryDetail:
        """One direct entry with everything its file says about it, plus that file's path.

        Read-only and addressed like remove/adopt (``source`` disambiguates a
        name two files share). Values are still the raw ones here — masking is
        the surface's job, and nothing below it logs them (``repr=False``).
        """
        spec, _text, parsed = await self.locate(uid, entry, source)
        (annotated,) = await self._annotate([parsed])
        return McpEntryDetail(entry=annotated, path=str(spec.path))

    async def locate(
        self, uid: str, entry: str, source: str | None
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
        cfg = await self._config_for(uid)
        specs = self.source_specs(cfg)
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
                    spec.format, text, source=spec.key, container_key=container_key(cfg.type)
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
        self, uid: str, entry: str, *, source: str | None = None, actor: str = "api"
    ) -> None:
        """Remove ``entry`` from the agent config file that contains it."""
        agent, cfg = await self.agent(uid)
        spec, _text, _parsed = await self.locate(uid, entry, source)
        # Re-read immediately before the write, as ``adopt`` does: ``locate``
        # awaits, so the text it returned can be stale by the time we get here.
        # The web UI deletes a whole selection at once and fans the requests out
        # concurrently, which puts several removals against ONE file in flight
        # together — computing each new text from its own pre-await snapshot
        # would let the last writer silently restore the entries the others
        # just removed.
        current = self._store.read_text(spec.path) or ""
        new_text = remove_entry_text(
            spec.format, current, entry, container_key=container_key(cfg.type)
        )
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_MCP_ENTRY_REMOVED.value,
            resource=agent,
            actor=actor,
            details={"entry": entry, "source": spec.key},
        )

    async def adopt(
        self,
        uid: str,
        entry: str,
        *,
        source: str | None = None,
        new_name: str | None = None,
        secrets: dict[str, str] | None = None,
        actor: str = "api",
    ) -> Resource:
        """Promote a config-file entry into a registered ``mcp_server`` resource.

        ``secrets`` maps secret-looking env/header KEY names to secret refs;
        every flagged key must be mapped (``AdoptSecretUnresolved`` otherwise).
        Secret VALUES go straight into the secret store and into
        ``secret_refs`` — never into the resource config, audit log, or
        any log line. Register + verify happen BEFORE the source entry is
        removed; a failure after registration deletes the new resource so the
        agent's file is never left without a working entry.
        """
        agent, cfg = await self.agent(uid)
        spec, _text, parsed_entry = await self.locate(uid, entry, source)

        flagged = secret_env_keys({**parsed_entry.env, **parsed_entry.headers})
        unresolved = [k for k in flagged if k not in (secrets or {})]
        if unresolved:
            raise AdoptSecretUnresolved(unresolved)

        # Narrow the caller-supplied mapping to keys that actually appear in the
        # entry's env or headers.  A key absent from both would still end up in
        # secret_refs (via to_transport_config) while the stored secret it
        # references was never written — dangling reference.
        # Coffer mints each secret's id (``secret/<uuid4 hex>``); the caller's
        # mapping says which keys carry a secret, and a ref it names is not used.
        provided = secrets or {}
        applicable = {
            k: secret_ref(mint_secret_name())
            for k in provided
            if k in parsed_entry.env or k in parsed_entry.headers
        }

        # A conflicting name is answered before anything is written, so the
        # caller can rename and retry without secrets having been touched.
        name = new_name or entry
        for existing in await self._rs.list(kind="mcp_server"):
            if existing.name == name:
                raise ResourceAlreadyExists("mcp_server", name)

        await write_new_refs(self._secrets, applicable, parsed_entry)

        config = {"transport": to_transport_config(parsed_entry, applicable)}
        try:
            # ResourceAlreadyExists bubbles — the route adds a rename suggestion.
            resource = await self._rs.register(
                kind="mcp_server", name=name, config=config, actor=actor
            )
        except Exception:
            await drop_new_refs(self._secrets, applicable)  # don't orphan just-written secrets
            raise
        try:
            # Verify the resource is really readable before touching the file.
            await self._rs.get(resource.uid)
            # Re-read the file immediately before the write to avoid a TOCTOU
            # window: another writer may have modified the file between locate
            # and here (two awaits above).
            current = self._store.read_text(spec.path) or ""
            try:
                new_text = remove_entry_text(
                    spec.format, current, entry, container_key=container_key(cfg.type)
                )
            except McpEntryNotFound:
                new_text = None  # entry vanished concurrently — nothing to remove
            if new_text is not None:
                self._store.write_text_atomic(spec.path, new_text)
        except Exception:
            # Roll back: never leave both a half-adopted resource AND a
            # still-present (or half-removed) config entry inconsistent.
            await self._rs.delete(resource.uid, actor=actor)
            await drop_new_refs(self._secrets, applicable)
            raise
        await self._audit.record(
            AuditEventType.AGENT_MCP_ENTRY_ADOPTED.value,
            resource=agent,
            actor=actor,
            details={"entry": entry, "resource": resource.name, "source": spec.key},
        )
        return resource
