"""Spawn ``opencode run --format json`` and expose its line-delimited events.

opencode's headless run mode emits one JSON value per line on stdout; each is (or
wraps) a message *part* — ``text`` / ``tool`` / ``step-start`` / ``step-finish`` /
``reasoning`` / … (opencode's OpenAPI ``Part`` union). This module owns the
subprocess seam (injectable for tests) and the argv construction; part
interpretation lives in :mod:`opencode_mapping`.

Only stdlib ``asyncio`` is used here — no third-party dependency.

.. note::
   opencode's live model calls could not be exercised end-to-end in the build
   sandbox (network egress to the model provider hangs), so the exact stdout
   framing is grounded in opencode's OpenAPI schema and its on-disk ``part``
   storage rather than a captured live run. :mod:`opencode_mapping` is therefore
   deliberately tolerant of both a raw-part line and a ``message.part.updated``
   event envelope; reconcile against a real stream on first use in a networked
   environment.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

#: A spawned opencode process. ``asyncio.subprocess.Process`` satisfies the shape
#: the adapter uses: ``.stdout`` / ``.stderr`` stream readers, ``await wait()``,
#: ``.returncode``, and ``.kill()``.
OpencodeProcess = asyncio.subprocess.Process

#: ``(argv, cwd, env) -> process`` — injectable so tests drive a canned stdout
#: stream without a real ``opencode`` binary or a model call.
OpencodeSpawner = Callable[
    [Sequence[str], str, "dict[str, str] | None"], Awaitable[OpencodeProcess]
]


def build_run_argv(
    prompt: str, *, resume_session: str | None, binary: str = "opencode"
) -> list[str]:
    """argv for one non-interactive opencode turn.

    ``--format json`` makes opencode print line-delimited part events instead of
    the formatted TUI output. ``--dangerously-skip-permissions`` keeps an
    unattended turn from blocking on an approval prompt — Coffer drives the agent,
    so the owner is the trust boundary (parity with Codex's ``approvalPolicy=never``
    / ``danger-full-access``). ``--session`` resumes the prior upstream session for
    multi-turn continuity. The prompt is the trailing positional message. The model
    is intentionally NOT passed: it comes from opencode's own config
    (``opencode.json`` ``model``), which Coffer's provider projection sets to
    ``coffer/<model>`` for a bound agent and leaves as opencode's default otherwise.
    """
    argv = [binary, "run", "--format", "json", "--dangerously-skip-permissions"]
    if resume_session:
        argv += ["--session", resume_session]
    argv.append(prompt)
    return argv


async def default_spawn(
    argv: Sequence[str], cwd: str, env: dict[str, str] | None
) -> OpencodeProcess:
    """Real subprocess spawn: ``opencode run …`` with stdout/stderr piped."""
    return await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


__all__ = ["OpencodeProcess", "OpencodeSpawner", "build_run_argv", "default_spawn"]
