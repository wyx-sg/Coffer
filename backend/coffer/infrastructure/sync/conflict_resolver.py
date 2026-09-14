"""A bounded agentic pass over a conflicted working tree (spec vault-sync ``## Conflicts``).

Implements ``application.sync.ports.ConflictResolverPort``. It is the middle
layer of three: credential blobs are settled by encryption time before they get
here, and anything this pass does not resolve stops the round so the user's own
git tools can.

Four properties are load-bearing, and each is a deliberate restriction:

* **It writes only into the git working tree.** The live vault is never
  touched. What it produces is a merge result like any other, and it reaches
  the vault only after the round's diff, guard and apply have had their say.
* **It is not trusted.** ``ConflictArbiter._passes_gate`` re-reads every file
  it claims and rejects one that still carries a conflict marker or no longer
  parses. This module therefore never has to be *right*, only bounded.
* **It is bounded.** A cap on how many files one pass will attempt, a cap on
  how large a file it will read, and a timeout on each model call and on the
  pass as a whole. A resolver that grinds forever over a hundred conflicted
  notes is worse than one that hands them to the user.
* **It never touches ``credentials/*.enc``.** Those are ordered by encryption
  time without the key, which is both cheaper and correct; asking a model to
  merge two ciphertexts could only produce a secret that decrypts to nothing.

Unavailable is a report, not a failure: with no internal model configured, "the
round stops and the user resolves it" is the designed fallback.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import Callable, Sequence
from typing import Protocol

from coffer.domain.provider.config import ResolvedConnection

_logger = logging.getLogger(__name__)

#: How many conflicted files one pass will attempt. Past this the divergence is
#: not a merge accident, and handing the whole set to the user beats spending a
#: model call each on a hundred of them.
MAX_PATHS = 20
#: The largest file the pass will read. A conflicted file carries both sides,
#: so the prompt is roughly this again; beyond it the merge is not something to
#: attempt in one shot.
MAX_BYTES = 96 * 1024
#: One model call. Generous, because a large merge is slow, and finite, because
#: a hung provider must not hold the vault-write lock indefinitely.
CALL_TIMEOUT_S = 90.0
#: The whole pass, so ``MAX_PATHS`` slow calls cannot add up to an hour.
PASS_TIMEOUT_S = 300.0

_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
_CREDENTIALS = "credentials/"

SYSTEM = (
    "You resolve a git merge conflict in one file of a user's personal vault. "
    "The file is given to you exactly as it sits in the working tree, with "
    "conflict markers in place.\n"
    "Return the ENTIRE merged file and nothing else — no explanation, no "
    "commentary, no code fence. Remove every conflict marker.\n"
    "PRESERVE INFORMATION. Both sides are the same user's own work from two of "
    "their machines, so the merged file normally contains what BOTH sides say. "
    "Combine them; drop something only when one side is plainly a corrected "
    "version of the other. Never invent content that is on neither side.\n"
    "Keep the file's existing format exactly: if it is YAML it must still "
    "parse as the same shape, if it is Markdown keep its headings and "
    "frontmatter. When you genuinely cannot tell how the two sides fit "
    "together, return the file unchanged with its markers, which tells the "
    "caller to leave it to the user."
)


class LlmCompletionPort(Protocol):
    """One-shot completion, seen as a sync-local protocol.

    Narrow on purpose: this pass wants one merged document back, not an agentic
    loop with tools. Reaching langchain through a port also keeps it out of
    this module (import contract 9).
    """

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ResolvedConnection,
        credential_resolver: Callable[[str], str],
    ) -> str: ...


class InternalModelPort(Protocol):
    """Coffer's own internal-engine connection, or None when unconfigured."""

    async def resolve_internal_connection(self) -> ResolvedConnection | None: ...


class AgenticConflictResolver:
    """Implements ``application.sync.ports.ConflictResolverPort`` structurally."""

    def __init__(
        self,
        *,
        worktree: pathlib.Path,
        completion: LlmCompletionPort,
        models: InternalModelPort,
        credential_resolver: Callable[[str], str],
        max_paths: int = MAX_PATHS,
        max_bytes: int = MAX_BYTES,
        call_timeout_s: float = CALL_TIMEOUT_S,
        pass_timeout_s: float = PASS_TIMEOUT_S,
    ) -> None:
        self._worktree = pathlib.Path(worktree)
        self._completion = completion
        self._models = models
        self._credential_resolver = credential_resolver
        self._max_paths = max_paths
        self._max_bytes = max_bytes
        self._call_timeout = call_timeout_s
        self._pass_timeout = pass_timeout_s

    async def available(self) -> bool:
        """Whether an internal model is configured on this machine.

        Answers False on any failure to find out. The caller's fallback for
        "unavailable" is to stop the round and tell the user, which is exactly
        the right response to a provider registry that cannot be read either.
        """
        try:
            return await self._models.resolve_internal_connection() is not None
        except Exception:
            _logger.warning("converge: could not resolve the internal model", exc_info=True)
            return False

    async def resolve(self, paths: Sequence[str]) -> list[str]:
        """Attempt the conflicts; return the paths it believes it resolved.

        "Believes" is the whole contract — the arbiter re-checks every path
        named here — so this reports optimistically and the gate is what makes
        the round safe.
        """
        model = await self._models.resolve_internal_connection()
        if model is None:
            return []
        attempts = [p for p in paths if not p.startswith(_CREDENTIALS)][: self._max_paths]
        if not attempts:
            return []
        resolved: list[str] = []
        try:
            async with asyncio.timeout(self._pass_timeout):
                for path in attempts:
                    if await self._resolve_one(path, model):
                        resolved.append(path)
        except TimeoutError:
            # Whatever was written before the clock ran out is still a merge
            # result the gate will judge on its own terms; the rest stays
            # conflicted and reaches the user.
            _logger.warning("converge: conflict pass timed out after %d file(s)", len(resolved))
        return resolved

    async def _resolve_one(self, path: str, model: ResolvedConnection) -> bool:
        target = self._worktree / path
        original = await asyncio.to_thread(self._read, target)
        if original is None:
            return False
        try:
            async with asyncio.timeout(self._call_timeout):
                merged = await self._completion.complete(
                    system=SYSTEM,
                    user=f"File: {path}\n\n{original}",
                    model=model,
                    credential_resolver=self._credential_resolver,
                )
        except (TimeoutError, asyncio.CancelledError):
            raise
        except Exception:
            # One file the model could not be asked about is not a failure of
            # the pass: the rest are still worth attempting, and this path
            # simply stays conflicted.
            _logger.warning("converge: conflict resolution failed for %s", path, exc_info=True)
            return False

        merged = _strip_fence(merged)
        if not merged.strip() or any(marker in merged for marker in _MARKERS):
            # The model was told to return the file unchanged when it cannot
            # tell how the sides fit; an empty answer means the same thing.
            return False
        await asyncio.to_thread(target.write_text, _newline_terminated(merged), "utf-8")
        return True

    def _read(self, target: pathlib.Path) -> str | None:
        """The conflicted file, or None when it is not something to attempt.

        A file that is too large, unreadable, binary, or no longer carrying a
        conflict marker is skipped rather than sent: a marker-free file is one
        git resolved by taking a whole side, and rewriting it would be this
        pass inventing a change nobody asked for.
        """
        try:
            if not target.is_file() or target.stat().st_size > self._max_bytes:
                return None
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return content if all(marker in content for marker in _MARKERS) else None


def _strip_fence(text: str) -> str:
    """Drop a wrapping code fence the model added despite being told not to.

    Only a fence that opens the first line and closes the last: anything else
    is content, and a Markdown note full of fenced examples must survive this
    untouched.
    """
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text


def _newline_terminated(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"
