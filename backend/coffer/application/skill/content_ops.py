"""Write-side helper for a skill's master-folder files.

A "helper module beside ``service.py``" like ``file_ops.py``: ``file_ops``
reads and guards paths; this adds the service-level concerns (existence,
the write through the vault's one write path with its fingerprint check,
audit) and is invoked by the HTTP surface. Kept out of ``service.py`` so that
file stays inside the component size cap.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from coffer.application.skill import file_ops
from coffer.application.skill.builtin_seed import is_builtin
from coffer.application.vault.ports import VaultWriterPort
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceProtected
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.layout import SKILLS
from coffer.domain.vault.writers import CommitMeta
from coffer.domain.workspace_errors import SkillFileStale

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


async def write_skill_file(
    service: SkillService,
    *,
    uid: str,
    relpath: str,
    content: str,
    expected_fingerprint: str,
    writer: VaultWriterPort,
    commit_for: Callable[[str], CommitMeta],
    actor: str = "api",
) -> file_ops.FileContent:
    """Overwrite one existing text file in a skill's master folder, as one
    vault commit.

    The master folder is the source of truth; delivered skills are links to
    it, so edited content reaches agents without re-delivery. It
    is also a folder the user edits directly in their own editor, so every
    write states ``expected_fingerprint`` — the fingerprint of the read that
    seeded the editor buffer — and the vault's one write path compares it
    under its lock before replacing the file (spec skill-manager "Save an
    existing skill file conditionally"; ADR
    every-vault-write-is-a-validated-commit-naming-its-writer: there is no
    unconditional mode). A mismatch is ``SkillFileStale`` (409) with the file
    byte-identical. ``commit_for`` gives the commit naming the writer for a
    summary; the commit is what the skill's History tab lists.

    A builtin skill's files are refused outright (``ResourceProtected`` →
    409): its master folder is rewritten from the running build at every
    start, so the edit would be lost silently — spec skill-manager
    "Regenerate Coffer's builtin skill from the build" says the surfaces must
    say so. Refusing here covers REST and CLI, not only the web viewer.

    Raises ``ResourceNotFound`` if the skill isn't registered,
    ``ResourceProtected`` for a builtin skill, ``SkillFileStale`` on a
    fingerprint mismatch, ``ValueError`` for a path outside the folder, content
    over ``file_ops.MAX_FILE_BYTES`` or a binary target, and
    ``FileNotFoundError`` when no such file exists (this edits files, it does
    not create them).
    """
    skill = await service.get_skill(uid)  # 404 if the skill isn't registered.
    if is_builtin(skill.config):
        raise ResourceProtected(
            f"skill {skill.name}",
            "its files are rewritten from the running build at every start, so "
            "an edit would not last; the correction belongs in Coffer's build",
        )
    # The master folder is named after the skill's name; the uid is how the
    # caller said which skill it meant.
    master = pathlib.Path(service.master_path(skill.name))
    # The reader runs the path-containment guard and the existence check, so a
    # path that escapes the folder is refused as an escape, never as stale.
    current = file_ops.read_skill_file(master, relpath)
    encoded = content.encode("utf-8")
    if len(encoded) > file_ops.MAX_FILE_BYTES:
        raise ValueError(f"content exceeds {file_ops.MAX_FILE_BYTES} bytes")
    if current.binary:
        # The editor only surfaces text files; a binary target is a malformed request.
        raise ValueError("refusing to overwrite a binary file with text")
    vault_path = f"{SKILLS}/{master.name}/{current.path}"
    meta = commit_for(f"Edit {skill.name}/{current.path}")
    try:
        version = await asyncio.to_thread(
            writer.write_file, vault_path, encoded, meta=meta, expected=expected_fingerprint
        )
    except VaultFileStale as exc:
        raise SkillFileStale(current.path) from exc
    await service._audit.record(
        AuditEventType.SKILL_UPDATED,
        resource=skill,
        actor=actor,
        details={"path": current.path, "edited_file": True, "version": version},
    )
    return file_ops.read_skill_file(master, relpath)
