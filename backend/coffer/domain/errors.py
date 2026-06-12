"""Domain-level error hierarchy; surfaces map these to HTTP status codes."""

from __future__ import annotations

from coffer.domain.error_base import CofferError as CofferError


class ResourceNotFound(CofferError):  # noqa: N818
    code = "RESOURCE_NOT_FOUND"

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"resource not found: {kind}:{name}")
        self.kind = kind
        self.name = name


class ResourceAlreadyExists(CofferError):  # noqa: N818
    code = "RESOURCE_ALREADY_EXISTS"

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"resource already exists: {kind}:{name}")
        self.kind = kind
        self.name = name


class UnknownKind(CofferError):  # noqa: N818
    code = "UNKNOWN_KIND"

    def __init__(self, kind: str) -> None:
        super().__init__(f"unknown kind: {kind!r}")
        self.kind = kind


class GenericCreateNotAllowed(CofferError):  # noqa: N818
    """The generic /resources endpoints cannot create or update this kind; a
    dedicated endpoint owns its lifecycle invariants. Maps to 409."""

    code = "GENERIC_CREATE_NOT_ALLOWED"

    def __init__(self, kind: str) -> None:
        super().__init__(
            f"kind {kind!r} cannot be created or updated via the generic "
            f"resources endpoint; use its dedicated endpoint"
        )
        self.kind = kind


class ConfigValidationError(CofferError):
    code = "CONFIG_INVALID"


class CredentialMissing(CofferError):  # noqa: N818
    code = "CREDENTIAL_MISSING"

    def __init__(self, ref: str) -> None:
        super().__init__(f"credential not found in keychain: {ref}")
        self.ref = ref


class CredentialLocked(CofferError):  # noqa: N818
    code = "CREDENTIAL_LOCKED"


class UpstreamUnavailable(CofferError):  # noqa: N818
    code = "UPSTREAM_UNAVAILABLE"


class UpstreamTimeout(CofferError):  # noqa: N818
    code = "UPSTREAM_TIMEOUT"


class ToolDisabled(CofferError):  # noqa: N818
    code = "TOOL_DISABLED"


class InvalidPrefix(CofferError):  # noqa: N818
    code = "INVALID_PREFIX"


class SkillDirNotWritable(CofferError):  # noqa: N818
    code = "SKILL_DIR_NOT_WRITABLE"

    def __init__(self, path: str, reason: str = "") -> None:
        msg = (
            f"skill_dir not writable: {path} ({reason})"
            if reason
            else f"skill_dir not writable: {path}"
        )
        super().__init__(msg)
        self.path = path
        self.reason = reason


class PrivilegedPath(CofferError):  # noqa: N818
    code = "PRIVILEGED_PATH"

    def __init__(self, path: str) -> None:
        super().__init__(f"path is privileged: {path}")
        self.path = path


class AgentConfigDirRegistered(CofferError):  # noqa: N818
    """An agent is already registered for this config directory. Maps to 409.

    config_dir is derived from the agent type, so this also means the type is
    already registered — only one agent per config directory is allowed.
    """

    code = "AGENT_CONFIG_DIR_REGISTERED"

    def __init__(self, config_dir: str, existing_name: str) -> None:
        super().__init__(
            f"an agent for config dir {config_dir} is already registered ({existing_name})"
        )
        self.config_dir = config_dir
        self.existing_name = existing_name


class ConfigFileNotAllowed(CofferError):  # noqa: N818
    """Requested config-file key is not in the agent type's allowlist.

    Surfaces map this to 404 — and crucially no filesystem access occurs for
    an unknown key.
    """

    code = "CONFIG_FILE_NOT_ALLOWED"

    def __init__(self, agent_type: str, key: str) -> None:
        super().__init__(f"config file key {key!r} not allowed for agent type {agent_type!r}")
        self.agent_type = agent_type
        self.key = key


class ConfigFileFormatInvalid(CofferError):  # noqa: N818
    """Content failed format validation (malformed JSON/TOML). Maps to 422."""

    code = "CONFIG_FILE_FORMAT_INVALID"

    def __init__(self, fmt: str, reason: str) -> None:
        super().__init__(f"invalid {fmt} content: {reason}")
        self.format = fmt
        self.reason = reason


class ShimNotFound(CofferError):  # noqa: N818
    """The coffer-mcp-shim binary could not be resolved. Maps to 422."""

    code = "SHIM_NOT_FOUND"

    def __init__(self, looked_for: str = "coffer-mcp-shim") -> None:
        super().__init__(f"could not resolve the {looked_for} binary on PATH or bundled location")
        self.looked_for = looked_for


class FsPathNotBrowsable(CofferError):  # noqa: N818
    """A folder-browse path can't be listed (missing, not a dir, unreadable).

    Surfaces map this to 400 — the caller-supplied path is invalid. No file
    contents are ever returned; this is a directory listing only.
    """

    code = "FS_PATH_NOT_BROWSABLE"

    def __init__(self, path: str, reason: str = "") -> None:
        msg = f"path not browsable: {path} ({reason})" if reason else f"path not browsable: {path}"
        super().__init__(msg)
        self.path = path
        self.reason = reason


# === skill manager ===


class SkillValidationError(CofferError):
    code = "SKILL_INVALID"

    def __init__(self, reason: str, details: dict[str, object] | None = None) -> None:
        super().__init__(f"skill folder invalid: {reason}")
        self.reason = reason
        self.details = details or {}


class SourceFetchError(CofferError):
    code = "SOURCE_FETCH_FAILED"

    def __init__(self, reason: str, details: dict[str, object] | None = None) -> None:
        super().__init__(f"source fetch failed: {reason}")
        self.reason = reason
        self.details = details or {}


class SSRFBlocked(CofferError):  # noqa: N818
    code = "SSRF_BLOCKED"

    def __init__(self, host: str) -> None:
        super().__init__(f"SSRF guard blocked outbound to: {host}")
        self.host = host


class TargetConflict(CofferError):  # noqa: N818
    code = "TARGET_CONFLICT"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"refusing to overwrite target ({reason}): {path}")
        self.path = path
        self.reason = reason


class SkillNameMismatch(CofferError):  # noqa: N818
    code = "SKILL_NAME_MISMATCH"

    def __init__(self, current: str, incoming: str) -> None:
        super().__init__(
            f"SKILL.md frontmatter name change: {current!r} -> {incoming!r}; "
            f"pass allow_rename=True to rename"
        )
        self.current = current
        self.incoming = incoming


class UpdateNotSupported(CofferError):  # noqa: N818
    """Raised when attempting to update a non-updatable source (e.g., local_import)."""

    code = "UPDATE_NOT_SUPPORTED"


class DatabaseSchemaTooNew(CofferError):  # noqa: N818
    """The on-disk DB was migrated by a newer/divergent Coffer build.

    Its Alembic revision is unknown to this build's migration tree, so
    ``upgrade head`` can't proceed. Surfaced at daemon startup with an
    actionable message instead of Alembic's opaque "Can't locate revision".
    """

    code = "DB_SCHEMA_TOO_NEW"

    def __init__(self, current: str, db_path: str) -> None:
        super().__init__(
            f"database schema revision {current!r} is newer than this Coffer "
            f"build understands — it was created by a newer or different version. "
            f"Upgrade Coffer, or back up and remove {db_path} to start fresh."
        )
        self.current = current
        self.db_path = db_path


# === agent workspace ===


class McpEntryNotFound(CofferError):  # noqa: N818
    """A named MCP config entry does not exist in any agent config file. Maps to 404."""

    code = "MCP_ENTRY_NOT_FOUND"

    def __init__(self, entry: str) -> None:
        super().__init__(f"MCP entry not found: {entry}")
        self.entry = entry


class McpEntryToggleUnsupported(CofferError):  # noqa: N818
    """The agent type does not support a per-entry enabled flag. Maps to 422."""

    code = "MCP_ENTRY_TOGGLE_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"per-entry enabled flag is not supported by {agent_type}")
        self.agent_type = agent_type


class McpEntryProtected(CofferError):  # noqa: N818
    """The entry is Coffer's own gateway entry and must not be mutated directly. Maps to 422."""

    code = "MCP_ENTRY_PROTECTED"

    def __init__(self, entry: str) -> None:
        super().__init__(
            f"entry {entry!r} is Coffer's own gateway entry; use the mcp-install operations"
        )
        self.entry = entry


class McpEntrySourceAmbiguous(CofferError):  # noqa: N818
    """The entry exists in multiple config files; the caller must name the source. Maps to 422."""

    code = "MCP_ENTRY_SOURCE_AMBIGUOUS"

    def __init__(self, entry: str) -> None:
        super().__init__(f"entry {entry!r} exists in multiple config files; specify the source")
        self.entry = entry


class AdoptSecretUnresolved(CofferError):  # noqa: N818
    """Secret-like env keys in a config snippet have no keychain mapping. Maps to 422."""

    code = "ADOPT_SECRET_UNRESOLVED"

    def __init__(self, keys: list[str]) -> None:
        self.keys = sorted(keys)
        super().__init__("secret-like env keys need a keychain mapping: " + ", ".join(self.keys))


class AgentConfigParseError(CofferError):
    """An agent config file could not be parsed. Maps to 422."""

    code = "AGENT_CONFIG_PARSE_ERROR"

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"cannot parse {path}: {detail}")
        self.path = path
        self.detail = detail


class PluginNotFound(CofferError):  # noqa: N818
    """A plugin identifier does not match any installed plugin. Maps to 404."""

    code = "PLUGIN_NOT_FOUND"

    def __init__(self, plugin_id: str) -> None:
        super().__init__(f"plugin not found: {plugin_id}")
        self.plugin_id = plugin_id


class PluginUninstallUnsupported(CofferError):  # noqa: N818
    """The agent type requires its own tooling to uninstall plugins. Maps to 422."""

    code = "PLUGIN_UNINSTALL_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"{agent_type} plugins must be uninstalled with the agent's own tooling")
        self.agent_type = agent_type


class ConfigFileStale(CofferError):  # noqa: N818
    """The file changed on disk since it was read; re-read and retry. Maps to 409."""

    code = "CONFIG_FILE_STALE"

    def __init__(self, key: str) -> None:
        super().__init__(f"config file {key!r} changed on disk since last read; re-read and retry")
        self.key = key


class UnmanagedSkillNotFound(CofferError):  # noqa: N818
    """An unmanaged skill name does not correspond to any discovered skill. Maps to 404."""

    code = "UNMANAGED_SKILL_NOT_FOUND"

    def __init__(self, name: str) -> None:
        super().__init__(f"unmanaged skill not found: {name}")
        self.name = name


class UnmanagedSkillInvalid(CofferError):  # noqa: N818
    """An unmanaged skill cannot be adopted because its folder is invalid. Maps to 422."""

    code = "UNMANAGED_SKILL_INVALID"

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"unmanaged skill {name!r} cannot be adopted: {reason}")
        self.name = name
        self.reason = reason


# --- knowledge_base kind (spec 006) -----------------------------------------


class KBNotFound(CofferError):  # noqa: N818
    code = "KB_NOT_FOUND"

    def __init__(self, kb_name: str) -> None:
        super().__init__(f"knowledge base not found: {kb_name!r}")
        self.kb_name = kb_name


class DocumentNotFound(CofferError):  # noqa: N818
    code = "DOCUMENT_NOT_FOUND"

    def __init__(self, kb_name: str, document_id: str) -> None:
        super().__init__(f"document not found: {kb_name}:{document_id}")
        self.kb_name = kb_name
        self.document_id = document_id


class IngestRejected(CofferError):  # noqa: N818
    code = "INGEST_REJECTED"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class EngineUnavailable(CofferError):  # noqa: N818
    """A converter library, sqlite-vec, or an embedding provider needed for the
    requested operation is unavailable. The caller degrades (vector→keyword) or
    surfaces a clear per-format error; the daemon stays up."""

    code = "ENGINE_UNAVAILABLE"

    def __init__(self, engine: str, detail: str) -> None:
        super().__init__(f"{engine} engine unavailable: {detail}")
        self.engine = engine
        self.detail = detail


class ReconversionBlocked(CofferError):  # noqa: N818
    """Re-converting a document whose ``source_mode == 'edited'`` is refused so
    hand edits are not clobbered; re-uploading a new source resets it."""

    code = "RECONVERSION_BLOCKED"

    def __init__(self, kb_name: str, document_id: str) -> None:
        super().__init__(
            f"cannot re-convert edited document {kb_name}:{document_id}; "
            "upload a new source file to reset source_mode to 'converted'"
        )
        self.kb_name = kb_name
        self.document_id = document_id


class GrepPatternInvalid(CofferError):  # noqa: N818
    """ripgrep rejected the pattern (exit code 2, e.g. invalid regex). Maps to
    400 — without this an rg failure masquerades as 'no matches'."""

    code = "GREP_PATTERN_INVALID"

    def __init__(self, pattern: str, detail: str) -> None:
        super().__init__(f"grep pattern rejected: {detail}")
        self.pattern = pattern
        self.detail = detail


class SearchModeInvalid(CofferError):  # noqa: N818
    """An explicit search mode the store cannot serve. Maps to 400.

    Raised for ``mode="grep"`` on the passage-search endpoint (grep has its own
    endpoint) and for an explicit mode the store has not enabled — instead of a
    silent rewrite. ``vector`` is the one exception: it degrades to keyword with
    a flagged fallback per the spec.
    """

    code = "SEARCH_MODE_INVALID"

    def __init__(self, mode: str, reason: str) -> None:
        super().__init__(f"search mode {mode!r} rejected: {reason}")
        self.mode = mode
        self.reason = reason


# --- memory kind (spec 007) -------------------------------------------------


class MemoryStoreNotFound(CofferError):  # noqa: N818
    code = "MEMORY_STORE_NOT_FOUND"

    def __init__(self, store_name: str) -> None:
        super().__init__(f"memory store not found: {store_name!r}")
        self.store_name = store_name


class MemoryNotFound(CofferError):  # noqa: N818
    code = "MEMORY_NOT_FOUND"

    def __init__(self, store_name: str, memory_id: str) -> None:
        super().__init__(f"memory not found: {store_name}:{memory_id}")
        self.store_name = store_name
        self.memory_id = memory_id


class MemoryRejected(CofferError):  # noqa: N818
    code = "MEMORY_REJECTED"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ScopeUnresolved(CofferError):  # noqa: N818
    """``scope=project`` was requested but the agent's cwd is not inside a git
    project, so no project ULID can be resolved. ``scope=global`` still works."""

    code = "SCOPE_UNRESOLVED"

    def __init__(self, cwd: str) -> None:
        super().__init__(
            f"cannot resolve a project memory scope: {cwd!r} is not inside a git "
            "project; use scope='global' instead"
        )
        self.cwd = cwd


class EmbeddingUnavailable(CofferError):  # noqa: N818
    """No embedding provider is configured / the provider failed to load.

    Never raised to the user for recall: ``vector`` degrades to ``keyword`` and
    flags the fallback. Used internally by the retrieval port to signal the
    degrade path.
    """

    code = "EMBEDDING_UNAVAILABLE"

    def __init__(self, detail: str) -> None:
        super().__init__(f"embedding unavailable: {detail}")
        self.detail = detail


# agent chat (spec 008): re-exported from coffer.domain.chat.errors (split for
# the file-size limit) so the coffer.domain.errors.X import paths keep working.
from coffer.domain.chat.errors import (  # noqa: E402, I001
    AgentConfigRejected as AgentConfigRejected,
    ApprovalNotFound as ApprovalNotFound,
    ConversationNotFound as ConversationNotFound,
    ModelNotFound as ModelNotFound,
    ModelRejected as ModelRejected,
    NoModelConfigured as NoModelConfigured,
    TurnInProgress as TurnInProgress,
    UnknownAgent as UnknownAgent,
)
