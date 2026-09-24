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
from coffer.application.skill.builtin_seed import is_builtin
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceProtected
from coffer.domain.workspace_errors import SkillFileStale

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


async def write_skill_file(
    service: SkillService,
    *,
    uid: str,
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

    A builtin skill's files are refused outright (``ResourceProtected`` →
    409): its master folder is rewritten from the running build at every
    start, so the edit would be lost silently — spec skill-manager
    "Regenerate Coffer's builtin skill from the build" says the surfaces must
    say so. Refusing here covers REST and CLI, not only the web viewer.

    Raises the same errors as :func:`file_ops.write_skill_file` (plus
    ``ResourceNotFound`` if the skill isn't registered, ``ResourceProtected``
    for a builtin skill, and ``SkillFileStale`` on a fingerprint mismatch).
    """
    skill = await service.get_skill(uid)  # 404 if the skill isn't registered.
    if is_builtin(skill.config):
        raise ResourceProtected(
            f"skill {skill.name}",
            "its files are rewritten from the running build at every start, so "
            "an edit would not last; the correction belongs in Coffer's build",
        )
    # The master folder is named after the skill's CURRENT label; the uid is
    # how the caller said which skill it meant. Reading the name off the row
    # we just resolved is what keeps a rename from stranding an editor.
    master = pathlib.Path(service.master_path(skill.name))
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
        resource=skill,
        actor=actor,
        details={"path": result.path, "edited_file": True},
    )
    return result
