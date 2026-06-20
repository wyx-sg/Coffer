"""AgentService — register / update / remove.

Wraps the kind-agnostic `ResourceService` with agent-specific concerns:
- I/O check for skill_dir writability (domain layer can't do this)
- Privileged-path defence

Detection is discovery-only (see ``AutoDetectService``): removing an agent
just deletes it, and the next scan re-surfaces it as a candidate — a removal
is never permanent, since it might have been accidental.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from collections.abc import Awaitable, Callable, Sequence

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import (
    AgentConfigDirRegistered,
    ConfigValidationError,
    PrivilegedPath,
    SkillDirNotWritable,
)
from coffer.domain.resource import Resource, ResourceRef

# Privileged path defence. Each entry is matched at component boundary (the
# entry itself or entry + os.sep) — so "/var" rejects "/var/run/x" but NOT
# "/var-tmp/x". Resolves before matching so symlinks can't sneak past.
_PRIVILEGED_PREFIXES_POSIX = (
    "/etc",
    "/bin",
    "/sbin",
    "/usr",
    "/var",
    "/sys",
    "/proc",
    "/root",
    "/boot",
    "/dev",
    "/System",
    "/Library/Application Support/Apple",
)
# Carve-outs INSIDE a privileged prefix that should still be usable. macOS's
# user temp area lives under ``/var/folders/<hash>`` (resolved from the
# /private firmlink); tests and ad-hoc tooling routinely place skills there.
# Anything below one of these prefixes is treated as non-privileged.
_PRIVILEGED_CARVE_OUTS_POSIX = ("/var/folders/",)
_PRIVILEGED_PREFIXES_WIN = (
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
)


def _is_privileged(s: str, prefixes: tuple[str, ...]) -> bool:
    sep = "\\" if sys.platform == "win32" else os.sep
    # Carve-outs take precedence — they MUST be considered safe even if they
    # nominally live under a privileged prefix (e.g. macOS /var/folders).
    if sys.platform != "win32" and any(s.startswith(c) for c in _PRIVILEGED_CARVE_OUTS_POSIX):
        return False
    return any(s == pfx or s.startswith(pfx + sep) for pfx in prefixes)


def _strip_macos_private(s: str) -> str:
    """On macOS several system roots are reached via the /private firmlink
    (``/etc`` → ``/private/etc``, ``/var`` → ``/private/var``). When we
    compare resolved paths against our prefix list we strip a leading
    ``/private`` so that the symlink-traversal attack surface collapses to
    the same prefix set we already maintain.
    """
    if sys.platform != "darwin":
        return s
    if s == "/private":
        return "/"
    if s.startswith("/private/"):
        return s[len("/private") :]
    return s


def assert_skill_dir_usable(path: pathlib.Path) -> None:
    """Raise SkillDirNotWritable / PrivilegedPath if the path can't host skills.

    Allowed: existing directory, writable by current user, not in a privileged
    system location.
    """
    resolved = path.expanduser().resolve()
    # Privileged-path defence. On macOS some system roots are accessed via
    # /private/<root>, so we strip that prefix and test both the unresolved-
    # but-expanded path and the fully-resolved path against the prefix set
    # using component-boundary matching (so "/var" rejects "/var/run/x" but
    # not "/var-tmp/x").
    unresolved = str(path.expanduser())
    s = str(resolved)
    prefixes = _PRIVILEGED_PREFIXES_WIN if sys.platform == "win32" else _PRIVILEGED_PREFIXES_POSIX
    candidates = (s, unresolved, _strip_macos_private(s), _strip_macos_private(unresolved))
    if any(_is_privileged(c, prefixes) for c in candidates):
        raise PrivilegedPath(s)
    # Existence + writability. FR-007 requires the skill_dir itself to be an
    # existing, writable directory — we do NOT silently accept a missing path
    # even if its parent is writable, because skill loading would then fail
    # later in obscure ways. The user must mkdir up front.
    if not resolved.is_dir():
        if not resolved.exists():
            raise SkillDirNotWritable(s, "directory_missing")
        raise SkillDirNotWritable(s, "not_a_directory")
    if not os.access(resolved, os.W_OK):
        raise SkillDirNotWritable(s, "not_writable")


class AgentService:
    """Agent-kind lifecycle on top of ResourceService."""

    def __init__(
        self,
        *,
        resource_service: ResourceService,
        audit: AuditService,
        on_config_dir_changed: Callable[[str], Awaitable[None]] | None = None,
        on_skill_policy_changed: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._rs = resource_service
        self._audit = audit
        # Cross-kind hooks (wired at the composition root). None in contexts
        # that don't manage skills.
        # - on_config_dir_changed: re-deliver an agent's skills after its
        #   config dir moves, so the old links aren't orphaned and the new
        #   dir isn't left empty.
        # - on_skill_policy_changed: reconcile deliveries with the agent's
        #   follow-master-library policy (FR-025) after registration or a
        #   policy update.
        self._on_config_dir_changed = on_config_dir_changed
        self._on_skill_policy_changed = on_skill_policy_changed

    async def register(
        self,
        *,
        agent_type: AgentType,
        name: str,
        config_dir: str | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        # Build + validate config (config_dir=None → the type's standard dir).
        try:
            cfg = AgentConfig(
                type=agent_type,
                config_dir=config_dir,
            )
        except Exception as e:  # pydantic ValidationError
            raise ConfigValidationError(str(e)) from e

        # Skills are delivered to <config_dir>/skills. Auto-create the skills/
        # leaf under an EXISTING config dir, then assert it's usable. We refuse
        # to create a missing config dir (a typo'd path must fail, not be
        # silently materialised).
        self._ensure_skill_dir(cfg.resolved_config_dir(), cfg.resolved_skill_dir())

        # Dedup by the resolved config dir — one agent per config directory.
        new_config_dir = str(cfg.resolved_config_dir())
        for existing in await self._rs.list(kind="agent"):
            try:
                existing_cfg = AgentConfig.model_validate(existing.config)
            except Exception:
                continue
            if str(existing_cfg.resolved_config_dir()) == new_config_dir:
                raise AgentConfigDirRegistered(new_config_dir, existing.name)

        registered = await self._rs.register(
            kind="agent",
            name=name,
            config=cfg.model_dump(mode="json"),
            description=description,
            actor=actor,
            allow_lifecycle_kind=True,  # CODE-REG: config dir detected/validated above
        )
        # New agents default to follow-all (FR-025): deliver the whole master
        # library now. Per-skill failures are tolerated inside the hook.
        if self._on_skill_policy_changed is not None:
            await self._on_skill_policy_changed(name)
        return registered

    @staticmethod
    def _ensure_skill_dir(config_dir: pathlib.Path, skill_dir: pathlib.Path) -> None:
        """Create the skill-delivery subpath under an EXISTING config dir, then
        assert it's usable.

        The agent's config dir (``~/.claude``, ``~/.codex``, …) must already
        exist — we refuse to ``mkdir -p`` a mistyped config location (e.g.
        ``/Usrs/me/.claude``) into being, which would silently deliver skills to
        a directory the agent never reads. The Coffer-owned skill subpath under
        it (``skills``) IS auto-created, including intermediate components.
        ``mkdir`` failures are swallowed — ``assert_skill_dir_usable`` surfaces
        the precise reason (privileged / not-writable / not-a-directory).
        """
        if not config_dir.is_dir():
            raise SkillDirNotWritable(str(config_dir), "directory_missing")
        with contextlib.suppress(OSError):
            # parents=True creates nested subpaths but never the config_dir
            # itself — that's guarded above.
            skill_dir.mkdir(parents=True, exist_ok=True)
        assert_skill_dir_usable(skill_dir)

    async def list(self) -> list[Resource]:
        return await self._rs.list(kind="agent")

    async def get(self, name: str) -> Resource:
        return await self._rs.get(ResourceRef("agent", name))

    async def update_config_dir(
        self,
        *,
        name: str,
        new_config_dir: str | None,
        actor: str = "api",
        description: str | None = None,
    ) -> Resource:
        existing = await self.get(name)
        cfg = AgentConfig.model_validate(existing.config)
        # `model_copy(update=...)` does NOT run validators (Pydantic v2). To
        # surface field-level errors as ConfigValidationError we go through
        # the model constructor, which runs validators. That also subsumes
        # the redundant re-validate that used to live below.
        try:
            # Merge over a dump of the CURRENT config so unrelated fields
            # (e.g. the FR-025 follow policy) can never be silently reset —
            # field enumeration here once dropped them when new fields landed.
            new_cfg = AgentConfig.model_validate(cfg.model_dump() | {"config_dir": new_config_dir})
        except Exception as e:  # pydantic ValidationError
            raise ConfigValidationError(str(e)) from e
        # Only run the I/O check (and create the skills subdir) when the
        # effective dir actually changes — a description-only PATCH must not
        # fail because the existing dir has become non-writable since register.
        dir_changed = new_cfg.resolved_config_dir() != cfg.resolved_config_dir()
        if dir_changed:
            self._ensure_skill_dir(new_cfg.resolved_config_dir(), new_cfg.resolved_skill_dir())
        updated = await self._rs.update_config(
            ResourceRef("agent", name),
            new_config=new_cfg.model_dump(mode="json"),
            actor=actor,
            description=description,
            allow_lifecycle_kind=True,  # CODE-REG: config dir validated above
        )
        # Re-deliver skills to the new location (remove old links, recreate at
        # <new_config_dir>/skills). Runs AFTER the row is updated so the hook
        # resolves the new dir. Without this the old links orphan and verify
        # falsely reports no drift.
        if dir_changed and self._on_config_dir_changed is not None:
            await self._on_config_dir_changed(name)
        return updated

    async def update_skill_policy(
        self,
        *,
        name: str,
        follow_all_skills: bool | None = None,
        # Sequence (not list) — the bare `list` name resolves to this class's
        # `list()` method inside the class body, so it isn't valid as a type.
        skill_exclusions: Sequence[str] | None = None,
        actor: str = "api",
    ) -> Resource:
        """Update the agent's follow-master-library policy (FR-025).

        ``None`` fields are left unchanged; both ``None`` is a no-op (the
        current resource is returned without an update or audit row). After a
        real update the on-skill-policy-changed hook reconciles deliveries
        (deliver newly wanted skills / remove newly excluded ones — disabling
        the flag preserves current bindings inside the hook).
        """
        existing = await self.get(name)
        if follow_all_skills is None and skill_exclusions is None:
            return existing
        cfg = AgentConfig.model_validate(existing.config)
        overrides: dict[str, object] = {}
        if follow_all_skills is not None:
            overrides["follow_all_skills"] = follow_all_skills
        if skill_exclusions is not None:
            overrides["skill_exclusions"] = list(skill_exclusions)
        try:
            # Merge over a full dump (see update_config_dir) so future
            # AgentConfig fields survive policy updates untouched.
            new_cfg = AgentConfig.model_validate(cfg.model_dump() | overrides)
        except Exception as e:  # pydantic ValidationError
            raise ConfigValidationError(str(e)) from e
        updated = await self._rs.update_config(
            ResourceRef("agent", name),
            new_config=new_cfg.model_dump(mode="json"),
            actor=actor,
            allow_lifecycle_kind=True,  # CODE-REG: value-level policy change only
        )
        # Reconcile AFTER the row is updated so the hook resolves the new
        # policy via the injected resolver.
        if self._on_skill_policy_changed is not None:
            await self._on_skill_policy_changed(name)
        return updated

    async def remove(self, *, name: str, actor: str = "api") -> None:
        # A removal is never permanent: detection is discovery-only, so the
        # next scan re-surfaces this agent as a candidate. We simply delete
        # the resource row (the generic ResourceService audits the deletion).
        await self._rs.delete(ResourceRef("agent", name), actor=actor)
