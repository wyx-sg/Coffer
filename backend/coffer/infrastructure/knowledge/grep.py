"""Ripgrep wrapper for the ``grep`` retrieval mode (no index).

Runs ``rg`` over a store's ``docs/`` directory, bounded by a max-match cap and a
wall-clock timeout. Falls back to ``EngineUnavailable`` if the ``rg`` binary is
absent. Output is parsed from ``--json`` so paths/line numbers are exact.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.retrieval import GrepHit, GrepResult

DEFAULT_MAX_MATCHES = 200
DEFAULT_TIMEOUT_S = 5.0

_logger = logging.getLogger(__name__)


class RipgrepGrep:
    """Implements the grep port via the ``rg`` binary."""

    def __init__(self, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._timeout = timeout_s

    async def grep(
        self,
        docs_dir: str,
        pattern: str,
        *,
        max_matches: int = DEFAULT_MAX_MATCHES,
    ) -> GrepResult:
        rg = shutil.which("rg")
        if rg is None:
            raise EngineUnavailable("ripgrep", "the 'rg' binary is not on PATH")
        root = Path(docs_dir)
        if not root.exists():
            return GrepResult()
        cap = max(1, max_matches)
        args = [
            rg,
            "--json",
            "--max-count",
            # One extra per file so a "more matches exist" overflow is visible.
            str(cap + 1),
            "--no-heading",
            "--",
            pattern,
            str(root),
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
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            # Kill the still-running rg (it would otherwise leak) and report
            # the truncation — a timeout is not "no matches".
            proc.kill()
            await proc.wait()
            _logger.warning(
                "knowledge.grep.timeout",
                extra={"docs_dir": docs_dir, "timeout_s": self._timeout},
            )
            return GrepResult(truncated=True)
        hits = _parse(stdout.decode("utf-8", errors="replace"), cap + 1)
        truncated = len(hits) > cap
        return GrepResult(hits=tuple(hits[:cap]), truncated=truncated)


def _parse(output: str, cap: int) -> list[GrepHit]:
    hits: list[GrepHit] = []
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
        path = str(data.get("path", {}).get("text", ""))
        line_number = int(data.get("line_number", 0))
        line = str(data.get("lines", {}).get("text", "")).rstrip("\n")
        hits.append(GrepHit(path=path, line_number=line_number, line=line))
        if len(hits) >= cap:
            break
    return hits
