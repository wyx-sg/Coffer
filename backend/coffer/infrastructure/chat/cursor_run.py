"""Spawn ``cursor-agent -p --output-format stream-json`` and expose its NDJSON.

Cursor's headless print mode emits line-delimited JSON (NDJSON): one JSON object
per line on stdout — a ``system`` init, ``assistant`` message segments,
``tool_call`` started/completed records, and a terminal ``result`` marker
(Cursor's CLI stream-json schema). This module owns the subprocess seam
(injectable for tests) and the argv construction; event interpretation lives in
:mod:`cursor_mapping`.

Only stdlib ``asyncio`` is used here — no third-party dependency.

.. note::
   ``cursor-agent`` is locked to Cursor's own backend and needs Cursor's own
   auth (``cursor-agent login`` / ``CURSOR_API_KEY``), so a live end-to-end run
   could not be exercised in the build sandbox. The stdout framing is grounded in
   Cursor's documented ``--output-format stream-json`` NDJSON schema rather than a
   captured live run; :mod:`cursor_mapping` is deliberately tolerant of
   missing/mis-typed fields. Reconcile against a real stream on first authenticated
   use.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

#: A spawned cursor-agent process. ``asyncio.subprocess.Process`` satisfies the
#: shape the adapter uses: ``.stdout`` / ``.stderr`` stream readers, ``await
#: wait()``, ``.returncode``, and ``.kill()``.
CursorProcess = asyncio.subprocess.Process

#: ``(argv, cwd, env) -> process`` — injectable so tests drive a canned stdout
#: stream without a real ``cursor-agent`` binary or a Cursor-backend call.
CursorSpawner = Callable[[Sequence[str], str, "dict[str, str] | None"], Awaitable[CursorProcess]]


def build_run_argv(
    prompt: str, *, resume_session: str | None, binary: str = "cursor-agent"
) -> list[str]:
    """argv for one non-interactive ``cursor-agent`` turn.

    ``-p`` (print) makes cursor-agent run headless and exit; ``--output-format
    stream-json`` makes it emit line-delimited JSON events instead of the
    formatted TUI output. ``--force`` auto-allows tool invocations (parity with
    Codex's ``approvalPolicy=never`` — Coffer drives the agent, so the owner is
    the trust boundary) and ``--trust`` trusts the headless workspace so a turn
    never blocks on a folder-trust prompt. ``--resume <chatId>`` continues the
    prior Cursor chat for multi-turn continuity. The prompt is the trailing
    positional message.

    The model is intentionally NOT passed: Cursor is locked to its own backend and
    uses the account's default model, so Coffer binds cursor to no model and
    projects no ``--model``.
    """
    argv = [binary, "-p", "--output-format", "stream-json", "--force", "--trust"]
    if resume_session:
        argv += ["--resume", resume_session]
    argv.append(prompt)
    return argv


#: StreamReader line-buffer limit for the subprocess pipes. cursor-agent emits one
#: JSON object per line, and a single ``tool_call`` completed ``result`` (a file
#: read or verbose command output) can exceed asyncio's 64 KiB default — which
#: would raise ``ValueError`` mid-stream. 16 MiB covers realistic outputs; the
#: adapter still degrades gracefully (skips the offending line) beyond it.
STREAM_LIMIT = 16 * 1024 * 1024


async def default_spawn(argv: Sequence[str], cwd: str, env: dict[str, str] | None) -> CursorProcess:
    """Real subprocess spawn: ``cursor-agent -p …`` with stdout/stderr piped."""
    return await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=STREAM_LIMIT,
    )


__all__ = ["CursorProcess", "CursorSpawner", "build_run_argv", "default_spawn"]
