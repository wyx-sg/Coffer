"""Spawn ``openclaw agent … --json --local`` and expose its result blob.

openclaw's headless turn (``openclaw agent --agent main --session-key <key>
-m <text> --json --local``) prints ONE clean JSON blob on stdout when the turn
completes — logs go to stderr. It is **NON-STREAMING** (Coffer's only such
provider — probe-verified on openclaw 2026.6.11): there are no incremental
events to parse, so this module owns only the subprocess seam (injectable for
tests) and the argv construction; blob interpretation lives in
:mod:`openclaw_mapping`.

``--local`` runs the fully-embedded agent — no gateway daemon needed, and the
plugin registry (incl. Coffer's dropped session-context extension, FR-048) is
preloaded fresh per run. The same ``--session-key`` maps to the same upstream
session, so Coffer derives a stable key from the conversation id instead of
discovering one from the stream. There is **no cwd flag**: the turn runs in the
agent's own workspace (``agents.defaults.workspace``), never the conversation's
working directory (see :mod:`openclaw_provider`).

Only stdlib ``asyncio`` is used here — no third-party dependency.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

#: A spawned openclaw process. ``asyncio.subprocess.Process`` satisfies the shape
#: the adapter uses: ``.stdout`` / ``.stderr`` stream readers, ``await wait()``,
#: ``.returncode``, and ``.kill()``.
OpenclawProcess = asyncio.subprocess.Process

#: ``(argv, cwd, env) -> process`` — injectable so tests drive a canned stdout
#: blob without a real ``openclaw`` binary or a model call.
OpenclawSpawner = Callable[
    [Sequence[str], str, "dict[str, str] | None"], Awaitable[OpenclawProcess]
]

#: The openclaw agent id Coffer drives. Every onboarded openclaw has a ``main``
#: agent; per-conversation isolation comes from the session KEY, not the agent.
OPENCLAW_AGENT_ID = "main"


def build_agent_argv(
    message: str,
    *,
    session_key: str,
    model: str | None = None,
    binary: str = "openclaw",
) -> list[str]:
    """argv for one non-interactive openclaw turn.

    ``--json`` makes openclaw print the result blob instead of formatted text;
    ``--local`` runs the embedded agent (no gateway daemon needed, fresh plugin
    registry per run). ``--session-key`` pins the upstream session for
    multi-turn continuity — Coffer chooses it deterministically per
    conversation. ``--model`` (``provider/model`` ref or model id) is passed
    only when the conversation carries an override; otherwise openclaw runs on
    its own configured ``agents.defaults.model.primary`` (which Coffer's
    provider projection sets to ``coffer/<model>`` for a bound agent).
    """
    argv = [binary, "agent", "--agent", OPENCLAW_AGENT_ID, "--session-key", session_key]
    if model:
        argv += ["--model", model]
    argv += ["-m", message, "--json", "--local"]
    return argv


#: StreamReader buffer limit for the subprocess pipes. The result blob includes
#: the full reply and an execution trace; a long agentic turn can exceed
#: asyncio's 64 KiB default. The adapter reads stdout to EOF (no line framing),
#: but stderr is drained line-wise, so the generous limit guards both.
STREAM_LIMIT = 16 * 1024 * 1024


async def default_spawn(
    argv: Sequence[str], cwd: str, env: dict[str, str] | None
) -> OpenclawProcess:
    """Real subprocess spawn: ``openclaw agent …`` with stdout/stderr piped."""
    return await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=STREAM_LIMIT,
    )


__all__ = [
    "OPENCLAW_AGENT_ID",
    "STREAM_LIMIT",
    "OpenclawProcess",
    "OpenclawSpawner",
    "build_agent_argv",
    "default_spawn",
]
