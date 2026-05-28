"""Domain-level error hierarchy.

Surfaces map these to HTTP status codes via FastAPI exception handlers.
"""

from __future__ import annotations


class CofferError(Exception):
    """Root of every domain-raised exception."""

    code: str = "INTERNAL_ERROR"


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


# === spec 005 — skill manager ===


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
    code = "ENGINE_UNAVAILABLE"

    def __init__(self, engine: str, detail: str) -> None:
        super().__init__(f"{engine} engine unavailable: {detail}")
        self.engine = engine
        self.detail = detail
