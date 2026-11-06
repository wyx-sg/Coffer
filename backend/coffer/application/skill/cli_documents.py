"""Every managed skill with its master SKILL.md, for the required-command
check (``SkillDocumentsPort``). Read at check time, never stored, so an edit
in the user's editor is what the next check sees."""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Sequence

from coffer.application.skill.cli_requirements import SkillDocument
from coffer.application.skill.service import SkillService


class MasterSkillDocuments:
    def __init__(self, skills: SkillService) -> None:
        self._skills = skills

    async def skill_documents(self) -> Sequence[SkillDocument]:
        rows = await self._skills.list_skills()
        pairs = [(r.uid, r.name, pathlib.Path(self._skills.master_path(r.name))) for r in rows]
        return await asyncio.to_thread(_read_all, pairs)


def _read_all(pairs: list[tuple[str, str, pathlib.Path]]) -> list[SkillDocument]:
    out: list[SkillDocument] = []
    for uid, name, folder in pairs:
        try:
            text: str | None = (folder / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
        out.append(SkillDocument(uid=uid, name=name, text=text))
    return out


__all__ = ["MasterSkillDocuments"]
