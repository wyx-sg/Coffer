"""Wire shapes of ``/api/v1/memory``."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryProjectOut(BaseModel):
    folder: str = Field(description="The project's folder under memory/projects/.")
    topics: int
    problems: int = Field(description="Files in it that break the memory format.")
    updated: str = Field(description="The newest `updated` date, or empty.")


class TidyHandoffOut(BaseModel):
    prompt: str


class MemoryStateOut(BaseModel):
    folder_path: str = Field(description="Absolute path of memory/projects/.")
    projects: list[MemoryProjectOut]
    tidy_running: bool
    tidy_started_at: float | None = None
    tidy_handoff: TidyHandoffOut


class MemoryTopicOut(BaseModel):
    project: str
    name: str
    title: str
    type: str = Field(description="user, feedback, project, or empty when the file names none.")
    updated: str
    body: str
    problems: list[str] = Field(
        description=(
            "What breaks the format: no_title, bad_type (type is not user, feedback or "
            "project), no_updated, no_memories, long_line (a line over 400 characters)."
        )
    )


class MemoryTopicListOut(BaseModel):
    project: str
    topics: list[MemoryTopicOut]


class MemoryFileOut(MemoryTopicOut):
    path: str = Field(description="Absolute path of the file.")
    text: str = Field(description="The whole file, frontmatter included.")
    digest: str = Field(description="Quote it as `expected` on an edit or delete.")


class MemoryFileIn(BaseModel):
    text: str
    expected: str


class MemoryTidyStatusOut(BaseModel):
    running: bool
    started_at: float | None = None


class MemoryTidyFinishIn(BaseModel):
    summary: str = ""


class MemoryTidyFinishOut(BaseModel):
    version: str | None = Field(description="The tidy's commit, or null when it changed nothing.")


class MemoryContextOut(BaseModel):
    text: str = Field(
        description="What a session started in `cwd` is handed; empty outside a project."
    )
