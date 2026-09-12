"""Ripgrep over the knowledge directory — the whole of literal retrieval.

There is no index behind this (spec knowledge FR-001), so ``rg`` is not a
fallback mode but the mechanism: it matches bytes, which means CJK matches
without a tokenizer, and it reads the files themselves, which means a human's
edit needs no import step to be findable.

``--no-hidden`` is passed explicitly even though it is ripgrep's default,
because a user's ``$RIPGREP_CONFIG_PATH`` could otherwise turn ``--hidden`` on
underneath us and start answering with the revisions in ``.history/`` (FR-052).
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import shutil

from coffer.domain.errors import EngineUnavailable, GrepPatternInvalid
from coffer.domain.knowledge.entry import GrepMatch, GrepOutcome
from coffer.infrastructure.knowledge import paths

DEFAULT_MAX_MATCHES = 200
DEFAULT_TIMEOUT_S = 5.0

_logger = logging.getLogger(__name__)


class RipgrepSearch:
    """Runs ``rg`` across a set of collection directories."""

    def __init__(self, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._timeout = timeout_s

    async def grep(
        self,
        roots: list[pathlib.Path],
        pattern: str,
        *,
        max_matches: int = DEFAULT_MAX_MATCHES,
    ) -> GrepOutcome:
        rg = shutil.which("rg")
        if rg is None:
            raise EngineUnavailable("ripgrep", "the 'rg' binary is not on PATH")
        present = [r for r in roots if r.exists()]
        if not present:
            return GrepOutcome()
        cap = max(1, max_matches)
        args = [
            rg,
            "--json",
            "--no-hidden",
            "--max-count",
            # One past the cap per file, so "more exist" is visible.
            str(cap + 1),
            "--no-heading",
            "--",
            pattern,
            *(str(r) for r in present),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:  # pragma: no cover - rg present but unexecutable
            raise EngineUnavailable("ripgrep", f"failed to run rg: {exc}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            # Kill the still-running rg — it would otherwise leak — and report
            # truncation, because a timeout is not "no matches".
            proc.kill()
            await proc.wait()
            _logger.warning("knowledge.grep.timeout", extra={"timeout_s": self._timeout})
            return GrepOutcome(truncated=True)
        # rg exits 0 on matches, 1 on none, 2 on error (an invalid regex, say).
        # An error must surface rather than masquerade as "no matches".
        if proc.returncode == 2:
            detail = stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise GrepPatternInvalid(pattern, detail[0] if detail else "ripgrep error")
        matches = _parse(stdout.decode("utf-8", errors="replace"), cap + 1)
        return GrepOutcome(matches=tuple(matches[:cap]), truncated=len(matches) > cap)


def _parse(output: str, cap: int) -> list[GrepMatch]:
    matches: list[GrepMatch] = []
    for raw in output.splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data", {})
        absolute = pathlib.Path(str(data.get("path", {}).get("text", "")))
        matches.append(
            GrepMatch(
                path=paths.relative_of(absolute),
                line_number=int(data.get("line_number", 0)),
                line=str(data.get("lines", {}).get("text", "")).rstrip("\n"),
            )
        )
        if len(matches) >= cap:
            break
    return matches
