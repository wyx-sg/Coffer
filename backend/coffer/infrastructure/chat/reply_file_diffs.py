"""What a Claude Code reply changed in each file (spec chat "Record what each
reply changed in each file").

Claude Code runs under ``bypassPermissions`` and writes files itself, so the
adapter watches the tool calls that can: a ``PreToolUse`` hook shows each path
BEFORE the write, and the first time a reply touches a path its content is kept.
When the reply ends the same paths are read again and compared. That is the
reply's own effect on each file, whatever the tool calls were and however many
of them there were — unlike ``git diff``, which is wrong outside a repository
and mixes in the owner's own uncommitted edits.

A file over 1 MB or not UTF-8 text is kept as counts only. A path whose content
ended identical is dropped. Files a Bash command wrote are not seen (they never
were in "Files changed" either). At most ``MAX_REPLY_FILES`` paths are watched
per reply.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import HookContext, HookInput, HookMatcher
from claude_agent_sdk.types import SyncHookJSONOutput

from coffer.domain.chat.reply_file import (
    MAX_DIFF_FILE_BYTES,
    MAX_REPLY_FILES,
    DiffOmitted,
    ReplyFile,
)

#: The tools whose calls the snapshot hook watches (a ``PreToolUse`` matcher).
WRITE_TOOLS_MATCHER = "Edit|MultiEdit|Write|NotebookEdit"

_NO_NEWLINE = "\\ No newline at end of file\n"
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class _Snap:
    """One file as it was at one moment."""

    present: bool
    digest: str = ""
    lines: int = 0
    #: The text, when it is small enough and valid UTF-8; else ``None``.
    text: str | None = None
    omitted: DiffOmitted | None = None


_ABSENT = _Snap(present=False, text="")


def _read(path: str) -> _Snap:
    """The file's content, a hash and line count of it, and its text when kept."""
    try:
        p = Path(path)
        if not p.is_file():
            return _ABSENT
        digest = hashlib.sha1(usedforsecurity=False)
        newlines = 0
        size = 0
        last = b""
        chunks: list[bytes] = []
        with p.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                size += len(chunk)
                digest.update(chunk)
                newlines += chunk.count(b"\n")
                last = chunk[-1:]
                if size <= MAX_DIFF_FILE_BYTES:
                    chunks.append(chunk)
    except OSError:
        return _ABSENT
    lines = newlines + (1 if size and last != b"\n" else 0)
    if size > MAX_DIFF_FILE_BYTES:
        return _Snap(True, digest.hexdigest(), lines, None, "too_large")
    data = b"".join(chunks)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _Snap(True, digest.hexdigest(), lines, None, "binary")
    if "\0" in text:
        return _Snap(True, digest.hexdigest(), lines, None, "binary")
    return _Snap(True, digest.hexdigest(), lines, text)


def _with_newline_marks(lines: list[str]) -> list[str]:
    return [ln if ln.endswith("\n") else ln + "\n" + _NO_NEWLINE for ln in lines]


def _diff(path: str, before: str, after: str) -> tuple[str | None, int, int]:
    """``(unified diff, added, removed)`` — the diff is ``None`` when the texts
    produce no hunk (only the presence of an empty file changed)."""
    name = path.lstrip("/")
    out = list(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            n=3,
        )
    )
    if not out:
        return None, 0, 0
    body = _with_newline_marks(out)
    added = sum(1 for ln in out[2:] if ln.startswith("+"))
    removed = sum(1 for ln in out[2:] if ln.startswith("-"))
    return "".join(body), added, removed


def _record(path: str, before: _Snap, after: _Snap) -> ReplyFile | None:
    if before.present == after.present and before.digest == after.digest:
        return None
    omitted = before.omitted or after.omitted
    if omitted is None and before.text is not None and after.text is not None:
        diff, added, removed = _diff(path, before.text, after.text)
        return ReplyFile(path, added, removed, diff)
    # Too large or not text: counts only, from the line totals either side.
    return ReplyFile(path, after.lines, before.lines, None, omitted)


class ReplyFileRecorder:
    """The files one reply wrote, from a snapshot before each first write."""

    def __init__(self, cwd: str) -> None:
        self._cwd = cwd
        self._before: dict[str, _Snap] = {}

    def resolve(self, raw: str) -> str:
        """The absolute, normalised path a tool call's path argument names."""
        return os.path.normpath(os.path.join(self._cwd, os.path.expanduser(raw)))

    def snapshot(self, raw: str) -> None:
        """Keep the file's content now, unless this reply has already touched it
        (the first snapshot is the one the reply is compared against)."""
        path = self.resolve(raw)
        if path in self._before or len(self._before) >= MAX_REPLY_FILES:
            return
        self._before[path] = _read(path)

    def files(self) -> list[ReplyFile]:
        """What the reply changed, first-touched file first; unchanged files left out."""
        recorded = (_record(path, before, _read(path)) for path, before in self._before.items())
        return [f for f in recorded if f is not None]


def write_hooks(recorder: ReplyFileRecorder) -> dict[Any, list[HookMatcher]]:
    """The ``ClaudeAgentOptions.hooks`` that snapshot each path a write tool is
    about to touch. ``PreToolUse`` hooks run in every permission mode, so they
    see the writes ``bypassPermissions`` never asks about; this one decides
    nothing and the permission mode carries on as it was."""

    async def snapshot(
        input_data: HookInput, _tool_use_id: str | None, _context: HookContext
    ) -> SyncHookJSONOutput:
        tool_input = cast(dict[str, Any], input_data).get("tool_input")
        if isinstance(tool_input, dict):
            raw = tool_input.get("file_path") or tool_input.get("notebook_path")
            if isinstance(raw, str) and raw:
                await asyncio.to_thread(recorder.snapshot, raw)
        return {}

    return {"PreToolUse": [HookMatcher(matcher=WRITE_TOOLS_MATCHER, hooks=[snapshot])]}
