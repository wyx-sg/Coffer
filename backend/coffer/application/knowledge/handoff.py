"""Working-state ("现场") handoff: one overwrite-per-branch file per project
store. Cross-agent + cross-machine continuity rides the file (git sync mirror).

The handoff lane is per (project store x git branch): parallel branches /
worktrees get independent scenes with no clobbering. There is no global handoff
(a global "current task" is meaningless) — ``resume`` returns ``None`` when the
cwd is not inside a git project. Files-as-truth: the markdown under
``projects/<ulid>/handoff/<branch-slug>.md`` is canonical; it is excluded from
recall (lives in the ``handoff/`` subdir the recall glob never descends into).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.scope import ScopeResolver, project_scope_name
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ScopeUnresolved
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.scope import KnowledgeScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.paths import handoff_path
from coffer.infrastructure.knowledge_scope import handoff_files as hf

#: Injected helpers (the service stays free of direct filesystem imports for the
#: branch read + the store-dir resolution, mirroring ``ScopeResolver``). The
#: branch reader matches ``scope_fs.git_branch`` (cwd is never ``None`` at the
#: call site — ``_locate`` short-circuits a ``None`` cwd first).
GitBranchFn = Callable[[str | Path], "str | None"]
ScopeDirFn = Callable[[str], Path]
ClockFn = Callable[[], datetime]


@dataclass(frozen=True)
class HandoffResult:
    """The outcome of a handoff write or read: the branch, the body, when it was
    last overwritten, and the store the handoff belongs to."""

    branch: str
    body: str
    updated_at: datetime
    scope_name: str


class HandoffService:
    """Save/restore the working-state handoff for the current project x branch."""

    def __init__(
        self,
        *,
        scope: ScopeResolver,
        git_branch: GitBranchFn,
        scope_dir: ScopeDirFn,
        audit: AuditService,
        now: ClockFn,
    ) -> None:
        self._scope = scope
        self._git_branch = git_branch
        self._scope_dir = scope_dir
        self._audit = audit
        self._now = now

    async def _locate(self, cwd: str | None) -> tuple[str, Path, str] | None:
        """Resolve ``(branch, handoff_path, scope_name)`` for ``cwd``, or
        ``None`` when there is no branch / no project scope (no global handoff)."""
        if cwd is None:
            return None
        branch = self._git_branch(cwd)
        if branch is None:
            return None
        try:
            resolved = await self._scope.resolve(scope=KnowledgeScope.PROJECT, cwd=cwd)
        except ScopeUnresolved:
            return None
        store_dir = self._scope_dir(resolved.resource_name)
        scope_name = project_scope_name(resolved.project_id)
        path = handoff_path(store_dir, hf.branch_slug(branch))
        return branch, path, scope_name

    async def set_handoff(self, *, cwd: str | None, body: str, actor: str) -> HandoffResult:
        """Overwrite the handoff for the current project x branch."""
        located = await self._locate(cwd)
        if located is None:
            raise ScopeUnresolved(cwd or "<none>")
        branch, path, scope_name = located
        ts = self._now()
        hf.write_handoff(path, branch=branch, body=body, updated_at=ts)
        await self._audit.record(
            AuditEventType.HANDOFF_SET.value,
            ref=ResourceRef(KIND_KNOWLEDGE, scope_name),
            actor=actor,
            details={"branch": branch, "char_size": len(body)},
        )
        return HandoffResult(branch=branch, body=body, updated_at=ts, scope_name=scope_name)

    async def resume(self, *, cwd: str | None) -> HandoffResult | None:
        """Return the saved handoff for the current project x branch, or ``None``."""
        located = await self._locate(cwd)
        if located is None:
            return None
        _branch, path, scope_name = located
        f = hf.read_handoff(path)
        if f is None:
            return None
        return HandoffResult(
            branch=f.branch, body=f.body, updated_at=f.updated_at, scope_name=scope_name
        )
