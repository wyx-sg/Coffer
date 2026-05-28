"""AgentService — register / update / remove + auto-detect suppression.

Wraps the kind-agnostic `ResourceService` with agent-specific concerns:
- I/O check for skill_dir writability (domain layer can't do this)
- Privileged-path defence
- Suppression-list integration (auto-detected agents removed by the user
  are not re-registered automatically; manual re-register lifts suppression)
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigValidationError,
    PrivilegedPath,
    SkillDirNotWritable,
)
from coffer.domain.resource import Resource, ResourceRef


class SuppressionRepoPort(Protocol):
    """Application-layer interface for the agent-type suppression list.

    The concrete implementation lives in
    ``coffer.infrastructure.agent.persistence.SuppressedAgentTypeRepo``;
    application code must not import that module directly (Contract 4).
    """

    async def is_suppressed(self, agent_type: str) -> bool: ...
    async def list_all(self) -> list[str]: ...
    async def suppress(self, agent_type: str) -> None: ...
    async def unsuppress(self, agent_type: str) -> None: ...


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
        suppression_repo: SuppressionRepoPort,
    ) -> None:
        self._rs = resource_service
        self._audit = audit
        self._suppression = suppression_repo

    async def register(
        self,
        *,
        agent_type: AgentType,
        name: str,
        skill_dir: str | None = None,
        description: str | None = None,
        actor: str = "api",
        auto_detected: bool = False,
    ) -> Resource:
        # Build + validate config
        try:
            cfg = AgentConfig(
                type=agent_type,
                skill_dir=skill_dir,
                auto_detected=auto_detected,
            )
        except Exception as e:  # pydantic ValidationError
            raise ConfigValidationError(str(e)) from e

        # I/O check on the resolved skill_dir
        assert_skill_dir_usable(cfg.resolved_skill_dir())

        # Persist as a Resource FIRST. We only lift suppression after the
        # resource row is committed so that a register failure (duplicate
        # name, validation, DB error) leaves any prior suppression intact.
        resource = await self._rs.register(
            kind="agent",
            name=name,
            config=cfg.model_dump(mode="json"),
            description=description,
            actor=actor,
        )
        # Lift any suppression for this type — manual re-register cancels it.
        await self._suppression.unsuppress(agent_type.value)
        return resource

    async def list(self) -> list[Resource]:
        return await self._rs.list(kind="agent")

    async def get(self, name: str) -> Resource:
        return await self._rs.get(ResourceRef("agent", name))

    async def update_skill_dir(
        self,
        *,
        name: str,
        new_skill_dir: str | None,
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
            new_cfg = AgentConfig(
                type=cfg.type,
                skill_dir=new_skill_dir,
                auto_detected=cfg.auto_detected,
            )
        except Exception as e:  # pydantic ValidationError
            raise ConfigValidationError(str(e)) from e
        # Only run the I/O check when the effective path actually changes —
        # a description-only PATCH must not fail because the existing
        # skill_dir has become non-writable since registration.
        if new_cfg.resolved_skill_dir() != cfg.resolved_skill_dir():
            assert_skill_dir_usable(new_cfg.resolved_skill_dir())
        return await self._rs.update_config(
            ResourceRef("agent", name),
            new_config=new_cfg.model_dump(mode="json"),
            actor=actor,
            description=description,
        )

    async def set_enabled(self, *, name: str, enabled: bool, actor: str = "api") -> Resource:
        return await self._rs.set_enabled(ResourceRef("agent", name), enabled=enabled, actor=actor)

    async def remove(self, *, name: str, actor: str = "api") -> None:
        # Look up first so we can decide if this is an auto-detected entry.
        snapshot = await self.get(name)
        cfg = AgentConfig.model_validate(snapshot.config)
        # Order matters: suppress BEFORE delete so the post-state is
        # consistent. If the delete fails, roll back the suppression so we
        # don't leave a phantom suppression with the resource still present.
        if cfg.auto_detected:
            await self._suppression.suppress(cfg.type.value)
            try:
                await self._rs.delete(ResourceRef("agent", name), actor=actor)
            except Exception:
                # Best-effort rollback. If unsuppress itself fails we let the
                # original exception propagate — the user can manually
                # `coffer agent detect` to re-create state.
                with contextlib.suppress(Exception):
                    await self._suppression.unsuppress(cfg.type.value)
                raise
            await self._audit.record(
                AuditEventType.AGENT_TYPE_SUPPRESSED.value,
                ref=ResourceRef("agent", name),
                actor=actor,
                details={"agent_type": cfg.type.value},
            )
        else:
            await self._rs.delete(ResourceRef("agent", name), actor=actor)
