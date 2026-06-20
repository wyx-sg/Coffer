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
from coffer.application.memory.scope import ScopeResolver, project_store_name
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ScopeUnresolved
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.memory.scope import MemoryScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.paths import handoff_path
from coffer.infrastructure.memory import handoff_files as hf

#: Injected helpers (the service stays free of direct filesystem imports for the
#: branch read + the store-dir resolution, mirroring ``ScopeResolver``).
GitBranchFn = Callable[[str | None], "str | None"]
StoreDirFn = Callable[[str], Path]
ClockFn = Callable[[], datetime]


@dataclass(frozen=True)
class HandoffResult:
    """The outcome of a handoff write or read: the branch, the body, when it was
    last overwritten, and the store the handoff belongs to."""

    branch: str
    body: str
    updated_at: datetime
    store_name: str


class HandoffService:
    """Save/restore the working-state handoff for the current project x branch."""

    def __init__(
        self,
        *,
        scope: ScopeResolver,
        git_branch: GitBranchFn,
        store_dir: StoreDirFn,
        audit: AuditService,
        now: ClockFn,
    ) -> None:
        self._scope = scope
        self._git_branch = git_branch
        self._store_dir = store_dir
        self._audit = audit
        self._now = now

    async def _locate(self, cwd: str | None) -> tuple[str, Path, str] | None:
        """Resolve ``(branch, handoff_path, store_name)`` for ``cwd``, or
        ``None`` when there is no branch / no project scope (no global handoff)."""
        branch = self._git_branch(cwd)
        if branch is None:
            return None
        try:
            resolved = await self._scope.resolve(scope=MemoryScope.PROJECT, cwd=cwd)
        except ScopeUnresolved:
            return None
        store_dir = self._store_dir(resolved.project_id)
        store_name = project_store_name(resolved.project_id)
        path = handoff_path(store_dir, hf.branch_slug(branch))
        return branch, path, store_name

    async def set_handoff(self, *, cwd: str | None, body: str, actor: str) -> HandoffResult:
        """Overwrite the handoff for the current project x branch."""
        located = await self._locate(cwd)
        if located is None:
            raise ScopeUnresolved(cwd or "<none>")
        branch, path, store_name = located
        ts = self._now()
        hf.write_handoff(path, branch=branch, body=body, updated_at=ts)
        await self._audit.record(
            AuditEventType.HANDOFF_SET.value,
            ref=ResourceRef(KIND_MEMORY, store_name),
            actor=actor,
            details={"branch": branch, "char_size": len(body)},
        )
        return HandoffResult(branch=branch, body=body, updated_at=ts, store_name=store_name)

    async def resume(self, *, cwd: str | None) -> HandoffResult | None:
        """Return the saved handoff for the current project x branch, or ``None``."""
        located = await self._locate(cwd)
        if located is None:
            return None
        _branch, path, store_name = located
        f = hf.read_handoff(path)
        if f is None:
            return None
        return HandoffResult(
            branch=f.branch, body=f.body, updated_at=f.updated_at, store_name=store_name
        )
