"""The Memory page's reads and a person's edits (spec memory "Show and edit
memory on the Memory page").

Every read is from disk: agents write the files themselves, and the page shows
what they wrote. A person's edit or delete is one vault commit, refused when
the file changed since the page read it.
"""

from __future__ import annotations

import asyncio
import pathlib
from dataclasses import dataclass

from coffer.domain.memory.hub import Topic
from coffer.infrastructure.memory.hub_store import HubStore, TopicFile


@dataclass(frozen=True)
class ProjectSummary:
    """One project folder as the page lists it."""

    folder: str
    topics: int
    #: Topics whose file breaks the format.
    problems: int
    #: The newest ``updated`` among its topics, ``""`` when none names one.
    updated: str


class MemoryService:
    def __init__(self, hub: HubStore | None = None) -> None:
        self._hub = hub or HubStore()

    @property
    def hub(self) -> HubStore:
        return self._hub

    def folder_path(self) -> str:
        root = self._hub.projects_root()
        home = pathlib.Path.home()
        try:
            return f"~/{root.relative_to(home).as_posix()}"
        except ValueError:
            return str(root)

    async def projects(self) -> list[ProjectSummary]:
        def _read() -> list[ProjectSummary]:
            out: list[ProjectSummary] = []
            for folder in self._hub.projects():
                topics = self._hub.topics(folder)
                out.append(
                    ProjectSummary(
                        folder=folder,
                        topics=len(topics),
                        problems=sum(1 for t in topics if t.problems),
                        updated=max((t.updated for t in topics), default=""),
                    )
                )
            return out

        return await asyncio.to_thread(_read)

    async def topics(self, project: str) -> list[Topic]:
        return await asyncio.to_thread(self._hub.topics, project)

    async def read(self, project: str, name: str) -> TopicFile:
        return await asyncio.to_thread(self._hub.read, project, name)

    async def write(self, project: str, name: str, text: str, *, expected: str, actor: str) -> None:
        await asyncio.to_thread(
            lambda: self._hub.write(project, name, text, expected=expected, actor=actor)
        )

    async def delete(self, project: str, name: str, *, expected: str, actor: str) -> None:
        await asyncio.to_thread(
            lambda: self._hub.delete(project, name, expected=expected, actor=actor)
        )


__all__ = ["MemoryService", "ProjectSummary"]
