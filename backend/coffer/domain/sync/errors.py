"""Sync error family (spec 010). Surfaces map these to HTTP status codes."""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.error_base import CofferError


class SyncNotConfigured(CofferError):  # noqa: N818
    """Sync has no remote configured / is disabled. Maps to 409."""

    code = "SYNC_NOT_CONFIGURED"

    def __init__(self, detail: str = "sync is not configured") -> None:
        super().__init__(detail)


class SyncInProgress(CofferError):  # noqa: N818
    """A sync run is already underway. Maps to 409."""

    code = "SYNC_IN_PROGRESS"

    def __init__(self) -> None:
        super().__init__("a sync run is already in progress")


class SyncConflict(CofferError):  # noqa: N818
    """A git merge left conflicting paths; the run imported nothing. Maps to 409."""

    code = "SYNC_CONFLICT"

    def __init__(self, paths: Sequence[str]) -> None:
        super().__init__(f"sync stopped on {len(paths)} conflicting path(s)")
        self.paths = list(paths)


class SyncWorkspaceTooNew(CofferError):  # noqa: N818
    """The workspace was written by a newer Coffer build. Maps to 409.

    Mirrors ``DB_SCHEMA_TOO_NEW``: refuse to import a layout this build does
    not understand instead of corrupting state.
    """

    code = "SYNC_WORKSPACE_TOO_NEW"

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"sync workspace schema version {found} is newer than this build "
            f"supports ({supported}); upgrade Coffer on this machine"
        )
        self.found = found
        self.supported = supported


class GitOperationFailed(CofferError):  # noqa: N818
    """A git subprocess returned non-zero for a non-conflict reason. Maps to 502."""

    code = "SYNC_GIT_FAILED"

    def __init__(self, operation: str, detail: str) -> None:
        super().__init__(f"git {operation} failed: {detail}")
        self.operation = operation
        self.detail = detail


class SyncRemoteUnreachable(CofferError):  # noqa: N818
    """The configured remote failed a reachability probe at save time. Maps to
    422 so the user fixes the URL/credentials in place instead of discovering
    the failure in a background run."""

    code = "SYNC_REMOTE_UNREACHABLE"

    def __init__(self, remote: str, hint: str | None, detail: str) -> None:
        super().__init__(f"remote unreachable: {detail}")
        self.remote = remote
        self.hint = hint
        self.detail = detail


# Signatures of headless git-auth failures → an actionable hint code the UI
# translates into guidance (use an SSH URL / run `gh auth setup-git`). The raw
# stderr stays in the message for diagnosis; the hint drives the friendly line.
_AUTH_SIGNATURES = (
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "authentication failed",
    "permission denied (publickey",
    "device not configured",
)
_NOT_FOUND_SIGNATURES = ("repository not found", "does not appear to be a git repository")
_NETWORK_SIGNATURES = (
    "could not resolve host",
    "connection refused",
    "connection timed out",
    "operation timed out",
    "network is unreachable",
)


def classify_git_error(text: str | None) -> str | None:
    """Map raw git stderr to a hint code: ``auth`` / ``not_found`` / ``network``.

    None when the text carries no recognizable transport signature (parse
    errors, conflicts, and engine errors are not transport problems).
    """
    if not text:
        return None
    lowered = text.lower()
    if any(sig in lowered for sig in _AUTH_SIGNATURES):
        return "auth"
    if any(sig in lowered for sig in _NOT_FOUND_SIGNATURES):
        return "not_found"
    if any(sig in lowered for sig in _NETWORK_SIGNATURES):
        return "network"
    return None


class MasterKeyFileInvalid(CofferError):  # noqa: N818
    """A master-key file to import is missing or not a valid Fernet key. Maps to 422."""

    code = "MASTER_KEY_FILE_INVALID"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"master key file invalid ({reason}): {path}")
        self.path = path
        self.reason = reason


class SyncSerializationError(CofferError):
    """A workspace resource document is malformed on import. Maps to 422."""

    code = "SYNC_SERIALIZATION_INVALID"

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid sync document: {detail}")
        self.detail = detail
