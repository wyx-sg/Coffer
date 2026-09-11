"""Write-side helper for a skill's master-folder files.

A "helper module beside ``service.py``" like ``file_ops.py``:
``file_ops`` does the pure filesystem write; this adds the service-level
concerns (existence check, optimistic-concurrency check, audit) and is invoked
by the HTTP surface. Kept out of ``service.py`` so that file stays inside the
component size cap.
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from coffer.application.skill import file_ops
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef
from coffer.domain.workspace_errors import SkillFileStale

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


async def write_skill_file(
    service: SkillService,
    *,
    name: str,
    relpath: str,
    content: str,
    expected_fingerprint: str | None = None,
    actor: str = "api",
) -> file_ops.FileContent:
    """Overwrite one existing text file in a skill's master folder.

    The master folder is the source of truth; FOLDER-delivered skills are
    symlinked to it, so edited content reaches agents without re-delivery. It
    is also a folder the user edits directly in their own editor, so a write
    may carry ``expected_fingerprint`` from the read that seeded the editor
    buffer: when it no longer matches the bytes on disk somebody else changed
    the file first, and we refuse (``SkillFileStale`` → 409) rather than
    silently discard their edit. The check runs before ``file_ops`` touches
    anything, so a rejected write leaves the file byte-identical.

    Omitting ``expected_fingerprint`` keeps the unconditional last-writer-wins
    write the programmatic (REST/CLI) clients relied on before the check
    existed.

    Raises the same errors as :func:`file_ops.write_skill_file` (plus
    ``ResourceNotFound`` if the skill isn't registered, and ``SkillFileStale``
    on a fingerprint mismatch).
    """
    await service.get_skill(name)  # 404 if the skill isn't registered.
    master = pathlib.Path(service.master_path(name))
    if expected_fingerprint is not None:
        # Reuse the reader so the path-containment guard runs identically here
        # and in the write below — a path that escapes the folder must be
        # rejected as an escape, never reported as a stale edit.
        current = file_ops.read_skill_file(master, relpath)
        if current.fingerprint != expected_fingerprint:
            raise SkillFileStale(current.path)
    result = file_ops.write_skill_file(master, relpath, content)
    await service._audit.record(
        AuditEventType.SKILL_UPDATED,
        ref=ResourceRef("skill", name),
        actor=actor,
        details={"path": result.path, "edited_file": True},
    )
    return result
