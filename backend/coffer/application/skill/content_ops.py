"""Write-side helper for a skill's master-folder files.

A "helper module beside ``service.py``" like ``file_ops.py`` / ``scan_ops.py``:
``file_ops`` does the pure filesystem write; this adds the service-level
concerns (existence check + audit) and is invoked by the HTTP surface. Kept out
of ``service.py`` so that file stays inside the component size cap.
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from coffer.application.skill import file_ops
from coffer.application.skill.scan_ops import rescan_skill
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


async def write_skill_file(
    service: SkillService, *, name: str, relpath: str, content: str, actor: str = "api"
) -> file_ops.FileContent:
    """Overwrite one existing text file in a skill's master folder.

    The master folder is the source of truth; FOLDER-delivered skills are
    symlinked to it, so edited content reaches agents without re-delivery.
    Raises the same errors as :func:`file_ops.write_skill_file` (plus
    ``ResourceNotFound`` if the skill isn't registered).
    """
    await service.get_skill(name)  # 404 if the skill isn't registered.
    master = pathlib.Path(service.master_path(name))
    result = file_ops.write_skill_file(master, relpath, content)
    await service._audit.record(
        AuditEventType.SKILL_UPDATED,
        ref=ResourceRef("skill", name),
        actor=actor,
        details={"path": result.path, "edited_file": True},
    )
    # The edit changed master content → re-scan (FR-028) and reset any prior
    # acknowledgment (it was for the pre-edit content).
    await rescan_skill(service=service, name=name, actor=actor, reset_acknowledgment=True)
    return result
