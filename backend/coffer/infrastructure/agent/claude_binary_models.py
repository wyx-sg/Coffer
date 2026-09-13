"""``ClaudeBinaryModelDiscovery`` — read Claude Code's tier aliases, and what
each one resolves to today, out of its own compiled binary.

WHY this exists at all. The CLI has no ``list models`` command and no local API
that answers "what can I run?", so the only machine-readable copy of that answer
on this machine is the one the CLI itself was built with. It ships as a single
bun-compiled executable that embeds a hand-maintained catalog, marked in the
bundle by a literal comment. Coffer reads that rather than writing anything
down, because a written-down list goes stale the day a release moves.

WHAT IS OFFERED: the four names the CLI itself lets a user pick — ``opus``,
``sonnet``, ``haiku``, ``fable`` — each labelled with the model it currently
means. Both halves come from the same embedded table: the catalog is followed by
an ``aliases`` object pairing every alias with the model it resolves to on a
first-party account, and the catalog entry for that model carries its display
name. So the picker offers ``opus`` and shows "Opus 5", and a CLI upgrade that
moves the alias onto a new release relabels the picker by itself.

WHY NOT THE VERSIONED CATALOG, which this source used to emit. That catalog is
cumulative and account-blind: it keeps every model the CLI has ever known —
including the internal families most accounts cannot run — and nothing on this
machine says which of them a given account may use. The CLI's own answer to that
question (``modelAccessCache`` in ``.claude.json``) is server-provided and
routinely empty, so no local rule can stand in for it. Offering the raw catalog
therefore filled the picker with names that fail the moment they are chosen. An
alias cannot fail that way: the CLI resolves it against the account at turn
time, which is precisely the knowledge Coffer does not have. Version information
is not lost in the trade — it moves into the label.

WHAT THIS COSTS, knowingly: a model that is not the current head of its family
can no longer be PICKED from this list. Nothing becomes unreachable — a model
NAME typed anywhere is passed to the CLI verbatim, and the account's own extra
options (a 1M-context variant, a promoted preview) still reach the picker from
``.claude.json`` through ``NativeConfigModelDiscovery``. The routing BEHAVIOURS
the CLI also accepts (``best``, ``opusplan``, the ``[1m]`` suffixes) stay out:
they are pointers and modifiers, not models, and the bundle marks them as such.

WHAT this costs when it breaks. The bundle's shapes are an implementation detail
of a release we do not control. If a future CLI renames the marker or changes
the table's layout, that anchor simply fails to match and this source returns
nothing. It cannot return wrong data, and it cannot fail a request.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import re
import shutil
from typing import IO

from coffer.domain.agent.model_catalogue import AgentModel

_log = logging.getLogger(__name__)

#: The agent type whose binary this adapter knows how to read.
_AGENT_KEY = "claude_code"

#: The comment the CLI's own authors put above the embedded catalog. It is the
#: only stable landmark in a minified 200 MB bundle.
_MARKER = b"Hand-maintained baked-in model catalog"

#: How much of the bundle to keep from the marker on. The catalog entries and
#: the alias table that follows them run a fair way past it; this is a generous
#: multiple of what was observed.
_AFTER = 128 * 1024

#: Streaming scan block size — the bundle is far too large to read whole.
_BLOCK = 4 * 1024 * 1024

#: Where the alias table starts, inside the window. It follows the catalog's
#: closing bracket, which is what keeps this from matching an ``aliases:``
#: elsewhere in the bundle.
_ALIASES_MARKER = b"],aliases:{"

#: How much of the window past that marker can be the table. It was ~450 bytes
#: when this was written; a generous multiple, and bounded so the tables that
#: follow it (``latest_per_family``, ``alias_migration``) stay out of reach.
_ALIASES_AFTER = 8 * 1024

#: One alias: its name and the model it resolves to on a first-party account.
#: The ``{default:"`` shape is the anchor — the sibling ``per_provider`` object
#: (deployments Coffer does not configure) opens with a provider name instead,
#: and ``latest_per_family`` holds bare strings, so neither can match.
_ALIAS_RE = re.compile(rb'([a-z][a-z0-9_]*):\{default:"(claude-[^"]+)"')

#: One catalog entry, read only for its display name. ``family`` is not used in
#: the output; it is here purely as an anchor, so a bare ``{id:"…"}`` elsewhere
#: in the bundle cannot match.
_ENTRY_RE = re.compile(rb'\{id:"(claude-[^"]+)",family:"[^"]+",display_name:"([^"]+)"')


class ClaudeBinaryModelDiscovery:
    """``ModelDiscoveryPort`` backed by the installed ``claude`` executable.

    Cached in-process on (resolved path, mtime, size): the scan touches a
    200 MB file, and the answer only changes when the CLI is upgraded — which
    replaces the symlink target, so the key changes with it.
    """

    def __init__(self, *, binary_name: str = "claude") -> None:
        self._binary_name = binary_name
        self._cache: tuple[tuple[str, int, int], list[AgentModel]] | None = None

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        """The CLI's tier aliases, labelled with the model each one is today.

        ``config_dir`` is unused: this reads the executable on PATH, which is
        the same one Coffer will spawn regardless of where the user's config
        lives.
        """
        if agent_key != _AGENT_KEY:
            return []
        # File I/O on a very large file — off the event loop (CODE-034), the
        # same rule the credential store follows.
        return await asyncio.to_thread(self._scan_cached)

    # --- internals -----------------------------------------------------------

    def _scan_cached(self) -> list[AgentModel]:
        path = self._resolve()
        if path is None:
            # Not installed. Deliberately NOT cached: the user may install the
            # CLI while the daemon is running, and re-checking PATH is cheap.
            return []
        try:
            stat = path.stat()
        except OSError:
            return []
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if self._cache is not None and self._cache[0] == key:
            return list(self._cache[1])
        models = self._scan(path)
        self._cache = (key, models)
        return list(models)

    def _resolve(self) -> pathlib.Path | None:
        """The real executable behind the launcher. ``resolve()`` matters: the
        entry on PATH is a symlink into a per-version directory, and the version
        directory is what makes the cache key move on upgrade."""
        found = shutil.which(self._binary_name)
        if found is None:
            return None
        try:
            return pathlib.Path(found).resolve()
        except OSError:
            return None

    def _scan(self, path: pathlib.Path) -> list[AgentModel]:
        """One streaming pass to the marker, then the slice it names.

        The catalog and the alias table sit within a few kilobytes of each other
        past the same marker, so one window carries both.
        """
        try:
            with path.open("rb") as fh:
                window = self._slice(fh, self._find_marker(fh, _MARKER))
        except OSError:
            _log.debug("agent.model_discovery.binary_unreadable path=%s", path, exc_info=True)
            return []
        if window is None:
            return []
        return self._aliases(window)

    @staticmethod
    def _find_marker(fh: IO[bytes], marker: bytes) -> int | None:
        """Absolute offset of the marker's FIRST occurrence, or ``None``.

        Consecutive blocks are stitched by an overlap of the marker's length so
        a landmark straddling a block boundary is still found.
        """
        overlap = len(marker) - 1
        consumed = 0
        tail = b""
        while True:
            block = fh.read(_BLOCK)
            if not block:
                return None
            buf = tail + block
            hit = buf.find(marker)
            if hit >= 0:
                return consumed - len(tail) + hit
            consumed += len(block)
            tail = buf[-overlap:] if overlap else b""

    @staticmethod
    def _slice(fh: IO[bytes], offset: int | None) -> bytes | None:
        """The window from ``offset`` on; ``None`` when the marker was absent."""
        if offset is None:
            return None
        fh.seek(offset)
        return fh.read(_AFTER)

    @staticmethod
    def _aliases(window: bytes) -> list[AgentModel]:
        """The alias table, in the bundle's own order, labelled from the catalog.

        An alias whose target the catalog does not describe keeps its own name
        as the label: a picker entry reading "Opus" is worse than one reading
        "Opus 5", but far better than an empty one.
        """
        start = window.find(_ALIASES_MARKER)
        if start < 0:
            return []
        table = window[start : start + _ALIASES_AFTER]
        display = {
            model_id.decode("utf-8", "replace"): name.decode("utf-8", "replace").strip()
            for model_id, name in _ENTRY_RE.findall(window)
        }
        out: list[AgentModel] = []
        for raw_alias, raw_target in _ALIAS_RE.findall(table):
            alias = raw_alias.decode("utf-8", "replace").strip()
            if not alias:
                continue
            target = raw_target.decode("utf-8", "replace").strip()
            out.append(AgentModel(id=alias, label=display.get(target) or alias.capitalize()))
        return out


__all__ = ["ClaudeBinaryModelDiscovery"]
