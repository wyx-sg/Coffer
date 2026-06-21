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


# credential-store error family: re-exported from coffer.domain.credential_errors
# (split for the file-size limit) so the coffer.domain.errors.X import paths keep working.
from coffer.domain.credential_errors import (  # noqa: E402, I001
    CredentialInUse as CredentialInUse,
    CredentialLocked as CredentialLocked,
    CredentialMissing as CredentialMissing,
    CredentialUnreadable as CredentialUnreadable,
    MasterKeyMissing as MasterKeyMissing,
)


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


class TargetConflict(CofferError):  # noqa: N818
    code = "TARGET_CONFLICT"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"refusing to overwrite target ({reason}): {path}")
        self.path = path
        self.reason = reason


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


# --- knowledge_base kind (spec 006) -----------------------------------------
# Canonical classes live in coffer.domain.kb_errors (split for the file-size
# limit); re-exported here so the coffer.domain.errors.X import paths keep working.
from coffer.domain.kb_errors import (  # noqa: E402, I001
    DocumentNotFound as DocumentNotFound,
    EngineUnavailable as EngineUnavailable,
    GrepPatternInvalid as GrepPatternInvalid,
    IngestRejected as IngestRejected,
    KBNotFound as KBNotFound,
    ReconversionBlocked as ReconversionBlocked,
    SearchModeInvalid as SearchModeInvalid,
)


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
    ConversationNotFound as ConversationNotFound,
    TurnInProgress as TurnInProgress,
    UnknownAgent as UnknownAgent,
)
