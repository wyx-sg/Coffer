"""Writing the rendered knowledge skill into each agent's skill directory.

The knowledge skill is **not** a skill-manager Resource, and that is the point
of this module existing separately from ``application.skill``. A managed skill
is one folder the user owns; this one is Coffer's own output, regenerated from
the corpus whenever the corpus changes, so it cannot be a row the user edits.

Every agent gets the same text — the corpus carries no per-agent reach, so
there is one catalogue and it is rendered once — but each agent still gets its
own real directory of its own real bytes (FR-035). That is not authorization;
it is that an agent reads only its own ``<config_dir>/skills/``, and the bytes
are Coffer's to own outright: never edited, and a person changing them loses
the change at the next pass. Nothing about them is a truth — the truth is
`topics/`, and this is a rendering of it. A vault upgraded from the earlier
shared-master delivery still has a symlink where one of those directories
belongs, which ``_replace`` removes rather than writes through.

Delivery is idempotent and never raises. A failure here leaves the layer
working — the files are still on disk at paths a person can give an agent — so
it must not be able to stop a boot or fail a curation pass.
"""

from __future__ import annotations

import logging
import pathlib
import shutil
from collections.abc import Awaitable, Callable, Sequence

from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.skill_render import SKILL_NAME, render
from coffer.infrastructure.knowledge import paths

logger = logging.getLogger(__name__)

#: Marks the directory as Coffer's output rather than a skill someone wrote,
#: for anyone who finds it in their own skills folder and wonders.
_README = (
    "# Generated\n\n"
    "`SKILL.md` in this folder is written by Coffer from the knowledge corpus "
    "and is rewritten whenever that corpus changes. Editing it has no lasting "
    "effect. The knowledge itself lives under `~/.coffer/knowledge/`.\n"
)

AgentLister = Callable[[], Awaitable[Sequence[object]]]
SkillDirResolver = Callable[[object], pathlib.Path]


class KnowledgeSkillDelivery:
    """Renders the knowledge skill once and writes it for every agent."""

    def __init__(
        self,
        *,
        service: KnowledgeService,
        list_agents: AgentLister,
        resolve_skill_dir: SkillDirResolver,
    ) -> None:
        self._service = service
        self._list_agents = list_agents
        self._resolve_skill_dir = resolve_skill_dir

    async def deliver_all(self) -> int:
        """Write every agent's copy. Returns how many actually changed.

        Safe to call on a timer: a copy whose rendered text already matches
        what is on disk is left alone, so the common tick costs a directory
        walk and two string comparisons rather than a write.

        The corpus is read and rendered once for the whole sweep, because the
        text does not vary by agent — a walk of every collection's ``topics/``
        lane per agent would be the same walk repeated.
        """
        try:
            agents = await self._list_agents()
        except Exception:
            logger.warning("knowledge.skill_delivery.list_agents_failed", exc_info=True)
            return 0
        try:
            text = render(str(paths.knowledge_root()), await self._service.catalogue())
        except Exception:
            # A corpus that cannot be read leaves every copy as it was, which
            # is the honest outcome: stale paths still resolve, and an empty
            # rendering would delete a catalogue over a transient read error.
            logger.warning("knowledge.skill_delivery.render_failed", exc_info=True)
            return 0
        written = 0
        for agent in agents:
            name = str(getattr(agent, "name", "") or "")
            if not name:
                continue
            if self._deliver_one(agent, name, text):
                written += 1
        return written

    def _deliver_one(self, agent: object, name: str, text: str) -> bool:
        try:
            folder = self._resolve_skill_dir(agent) / SKILL_NAME
            changed = _replace(folder, text)
        except Exception:
            # One agent's directory being unwritable must not stop the others,
            # and must not fail whatever armed this.
            logger.warning(
                "knowledge.skill_delivery.failed",
                extra={"agent": name},
                exc_info=True,
            )
            return False
        return changed


def _replace(folder: pathlib.Path, text: str) -> bool:
    """Put ``text`` at ``folder/SKILL.md``; return whether anything changed.

    A symlink is removed rather than followed: a vault upgraded from the
    shared-master delivery has one here, and writing through it would edit the
    master every other agent still points at. Note the branch order — a link is
    replaced *without* comparing text, because a copy that merely happens to
    match is still not the independent file FR-035 asks for. That matters even
    though every agent's text is identical: the master is outside every agent's
    directory, so nothing regenerates it and it is the one file here that can
    go stale without anyone noticing.
    """
    target = folder / "SKILL.md"
    if folder.is_symlink():
        folder.unlink()
    elif folder.is_dir() and target.is_symlink():
        target.unlink()
    elif target.is_file():
        try:
            if target.read_text(encoding="utf-8") == text:
                return False
        except OSError:
            pass
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / ".SKILL.md.tmp"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    (folder / "README.md").write_text(_README, encoding="utf-8")
    return True


def remove_shared_master(master_root: pathlib.Path) -> None:
    """Delete the old shared master folder, if the upgrade left one behind.

    Called once by the migration. It is here rather than in the migration so
    the knowledge layer keeps the knowledge of what its own delivery used to
    look like.
    """
    folder = master_root / SKILL_NAME
    if folder.is_dir() and not folder.is_symlink():
        shutil.rmtree(folder, ignore_errors=True)


__all__ = ["KnowledgeSkillDelivery", "remove_shared_master"]
