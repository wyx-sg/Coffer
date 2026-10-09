"""Domain-level error hierarchy; surfaces map these to HTTP status codes."""

from __future__ import annotations

from coffer.domain.error_base import CofferError as CofferError


class ResourceNotFound(CofferError):  # noqa: N818
    """Nothing answers to what the caller asked for.

    Carries the SUBJECT the caller used, not a canonical identifier: a lookup
    by uid has no name to report, and one that started from a label the user
    typed must echo that label back or the message helps nobody. Use
    :meth:`named` on the label path so the two phrasings stay in one place.
    """

    code = "RESOURCE_NOT_FOUND"

    def __init__(self, subject: str) -> None:
        super().__init__(f"resource not found: {subject}")
        self.subject = subject

    @classmethod
    def named(cls, kind: str, name: str) -> ResourceNotFound:
        return cls(f"no {kind} named {name!r}")


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


class NameImmutable(CofferError):  # noqa: N818
    """A changed name for a resource whose kind declares its name fixed.

    The name is quoted outside Coffer — an MCP server's name prefixes every
    tool name an agent sees, a skill's is the folder an agent loads it from —
    so a rename would break whatever quotes it (ADR
    names-visible-to-agents-are-fixed). The message names the only way to a
    new name and what it resets. Maps to 409.
    """

    code = "NAME_IMMUTABLE"

    def __init__(self, kind: str, name: str, resets: str, *, derived: bool = False) -> None:
        if derived:
            # ``Kind.name_from_config``: the name IS the type, so there is no
            # other name to register it under.
            message = f"the name of {kind} {name!r} is its type and cannot change"
        else:
            cost = f", which resets {resets}" if resets else ""
            message = (
                f"the name of {kind} {name!r} cannot change: it is quoted outside Coffer. "
                f"To use a new name, delete it and register it again under that name{cost}."
            )
        super().__init__(message)
        self.kind = kind
        self.name = name


class ConfigValidationError(CofferError):
    code = "CONFIG_INVALID"


class ScopeInvalidError(CofferError):
    """A per-agent activation-scope payload failed validation (ADR per-agent-resource-scope):
    either the kind does not declare ``supports_scope`` (it carries no scope at
    all) or the payload's shape is not an agent allow-list.

    Deliberately its own class rather than reusing ConfigValidationError so
    surfaces can map it to a dedicated envelope code (SCOPE_INVALID) the
    frontend keys off — still a CofferError subclass so the sync importer's
    broad ``except CofferError`` quarantine handling keeps covering it.
    """

    code = "SCOPE_INVALID"


class UpstreamUnavailable(CofferError):  # noqa: N818
    code = "UPSTREAM_UNAVAILABLE"


class UpstreamAuthRejected(UpstreamUnavailable):
    """The upstream HTTP endpoint answered 401 or 403: the key it was given is
    refused. Reaches callers as the same ``UPSTREAM_UNAVAILABLE`` envelope."""


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


class AgentConfigDirMissing(CofferError):  # noqa: N818
    """An agent's config dir does not exist on this machine.

    Raised by the sync import gate, where it means "this document is for an
    agent not installed here" — not applicable, rather than a failure to retry
    every round (spec vault-sync). The front door (``AgentService.register``)
    still reports a missing dir as ``SkillDirNotWritable``.
    """

    code = "AGENT_CONFIG_DIR_MISSING"

    def __init__(self, path: str) -> None:
        super().__init__(f"agent config dir does not exist on this machine: {path}")
        self.path = path


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


class AgentTypeRegistered(CofferError):  # noqa: N818
    """An agent of this type is already registered: there is one per type on a
    machine (spec agent-registry "Keep one agent per type, named by it"). Maps
    to 409; moving it to another directory is the existing agent's edit."""

    code = "AGENT_TYPE_REGISTERED"

    def __init__(self, agent_type: str, existing_uid: str) -> None:
        super().__init__(
            f"a {agent_type} agent is already registered ({existing_uid}); "
            "change its config directory instead of adding a second one"
        )
        self.agent_type = agent_type
        self.existing_uid = existing_uid


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
    """The coffer-mcp-shim binary could not be resolved (422); carries the hand-off prompt."""

    code = "SHIM_NOT_FOUND"

    def __init__(self, looked_for: str = "coffer-mcp-shim", handoff: str | None = None) -> None:
        super().__init__(f"could not resolve the {looked_for} binary on PATH or bundled location")
        self.error_details = {"handoff": {"prompt": handoff}} if handoff else {}


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


class FsPathNotOpenable(CofferError):  # noqa: N818
    """An open/reveal target can't be acted on (not absolute, missing, launch failed).

    Surfaces map this to 400 — the caller-supplied path is invalid or the OS
    launcher could not be spawned. The daemon acts only on an existing absolute
    path; it never creates anything (spec daemon "Open and reveal existing
    absolute paths",
    ADR: daemon-proxies-os-file-actions).
    """

    code = "FS_PATH_NOT_OPENABLE"

    def __init__(self, path: str, reason: str = "") -> None:
        msg = f"path not openable: {path} ({reason})" if reason else f"path not openable: {path}"
        super().__init__(msg)
        self.path = path
        self.reason = reason


# === skill manager ===


class SkillValidationError(CofferError):
    code = "SKILL_INVALID"

    def __init__(self, reason: str, details: dict[str, object] | None = None) -> None:
        self.reason = reason
        self.details = details or {}
        super().__init__(f"skill folder invalid: {reason}{_describe_skill_details(self.details)}")


def _describe_skill_details(details: dict[str, object]) -> str:
    """The part of a skill-validation message that says what is actually wrong.

    The reason code alone ("skill_md_frontmatter_invalid") leaves the author to
    rediscover which field broke which rule; the validator already holds that.
    """
    errors = details.get("errors")
    if isinstance(errors, list) and errors:
        parts = []
        for e in errors:
            if not isinstance(e, dict):
                continue
            loc = ".".join(str(p) for p in e.get("loc", ())) or "frontmatter"
            parts.append(f"{loc}: {e.get('msg', 'invalid')}")
        if parts:
            return " — " + "; ".join(parts)
    path = details.get("path")
    if isinstance(path, str) and path:
        return f" ({path})"
    return ""


class UpkeepAlreadyRunning(CofferError):  # noqa: N818
    """A long upkeep pass over this target is already in flight.

    Memory's organise and knowledge's tidy both rewrite a whole directory with
    a model in the loop; two of them over the same target at once are two
    writers racing, not one faster pass. Surfaces map this to 409 — the
    request is refused, and the caller's own display should already have been
    saying "running" (``application.upkeep_runs``).
    """

    code = "UPKEEP_ALREADY_RUNNING"

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"an upkeep pass is already running for {kind}:{name}")
        self.kind = kind
        self.name = name


class ResourceProtected(CofferError):  # noqa: N818
    """A resource Coffer owns outright, asked to be taken over.

    Raised for the two ways that can be asked: deleting it, and importing over
    its name. Neither would stick — the same daemon writes the resource back at
    the next boot — so both read as decisive and behave as no-ops. The honest
    answer is to refuse and say which resource it is, which is why the verb
    lives in ``reason`` rather than in the message prefix: one class, two
    refusals, each able to say what it is actually refusing.

    Disabling the resource, or narrowing its scope, stays available: those
    decide reach, which is the owner's to decide, while existence is not.
    """

    code = "RESOURCE_PROTECTED"

    def __init__(self, ref: str, reason: str) -> None:
        super().__init__(f"{ref} is managed by Coffer: {reason}")
        self.ref = ref
        self.reason = reason


class ResourceNotToggleable(CofferError):  # noqa: N818
    """Enabling or disabling a resource whose kind has no enabled switch.

    A kind that declares ``toggleable=False`` serves every one of its resources
    (spec resource-framework "Address every resource by an immutable uid
    through one kind-agnostic surface"), so the switch is refused rather than
    stored as a flag nothing reads. Maps to 409.
    """

    code = "RESOURCE_NOT_TOGGLEABLE"

    def __init__(self, kind: str, uid: str) -> None:
        super().__init__(f"{kind} resources cannot be enabled or disabled: {uid}")
        self.kind = kind
        self.uid = uid


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


# --- knowledge layer: a missing converter backend ---------------------------
# Canonical classes live in coffer.domain.kb_errors (split for the file-size
# limit); re-exported here so the coffer.domain.errors.X import paths keep working.
from coffer.domain.kb_errors import (  # noqa: E402
    EngineUnavailable as EngineUnavailable,
)


class InvocationNotFound(CofferError):  # noqa: N818
    """No call in the invocation log has this id (it never existed, or retention pruned it)."""

    code = "INVOCATION_NOT_FOUND"

    def __init__(self, invocation_id: int) -> None:
        super().__init__(f"no call with id {invocation_id} in the invocation log")
