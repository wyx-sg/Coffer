"""``ClaudeBinaryModelDiscovery`` — read Claude Code's model list out of its own
compiled binary.

WHY this exists at all. The CLI has no ``list models`` command and no local API
that answers "what can I run?", so the only machine-readable copy of that answer
on this machine is the one the CLI itself was built with. It ships as a single
bun-compiled executable that embeds a hand-maintained catalog (marked in the
bundle by a literal comment) plus the alias array its ``--model`` flag accepts.
Coffer reads both rather than writing the names down, because a written-down
list goes stale and — more importantly — an alias like the newest-Opus pointer
cannot tell the user WHICH Opus they are about to run. The catalog carries the
version in every display name; that is the whole point of reading it.

WHAT this costs when it breaks. The bundle's shapes are an implementation
detail of a release we do not control. If a future CLI renames the marker or
changes the literal layout, every anchor here simply fails to match and the
source returns nothing — the picker falls back to the other sources. It cannot
return wrong data, and it cannot fail a request.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import re
import shutil

from coffer.domain.agent.model_catalogue import AgentModel

_log = logging.getLogger(__name__)

#: The agent type whose binary this adapter knows how to read.
_AGENT_KEY = "claude_code"

#: The comment the CLI's own authors put above the embedded catalog. It is the
#: only stable landmark in a minified 200 MB bundle.
_MARKER = b"Hand-maintained baked-in model catalog"

#: How much of the bundle to keep around the marker. The alias arrays sit a
#: little BEFORE the marker and the catalog entries a fair way after it, so the
#: window is asymmetric. Both are generous multiples of what was observed.
_BEFORE = 16 * 1024
_AFTER = 128 * 1024

#: Streaming scan block size — the bundle is far too large to read whole.
_BLOCK = 4 * 1024 * 1024

#: One catalog entry. ``family`` is not used in the output; it is here purely as
#: an anchor, so a bare ``{id:"…"}`` elsewhere in the bundle cannot match.
_ENTRY_RE = re.compile(
    rb'\{id:"(claude-[^"]+)",family:"[^"]+",display_name:"([^"]+)"'
    rb'(?:,knowledge_cutoff:"([^"]*)")?'
)

#: The alias array, located STRUCTURALLY so no alias is ever written down here.
#: The bundle declares the id array first and the alias array immediately after
#: it in the same statement; variable names are minified and change every
#: release, so the anchor is "an array whose every member carries the vendor
#: prefix, then the next array literal that is assigned to something".
_ALIAS_RE = re.compile(
    rb'\[(?:"claude-[^"]*"\s*,\s*)+"claude-[^"]*"\]'
    rb"\s*[,;]\s*(?:var\s+)?[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*"
    rb'\[((?:"[^"]*"\s*,\s*)*"[^"]*")\]'
)

_STRING_RE = re.compile(rb'"([^"]*)"')


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
        """The aliases the CLI accepts, then its versioned catalog.

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
        window = self._read_window(path)
        if window is None:
            return []
        before, after = window
        return self._aliases(before) + self._catalog(after)

    @staticmethod
    def _read_window(path: pathlib.Path) -> tuple[bytes, bytes] | None:
        """Stream the bundle looking for the marker, then re-read the slice
        around it. Returns ``(bytes before the marker, bytes from the marker
        on)``, or ``None`` if the marker is absent."""
        overlap = len(_MARKER) - 1
        try:
            with path.open("rb") as fh:
                consumed = 0
                tail = b""
                while True:
                    block = fh.read(_BLOCK)
                    if not block:
                        return None
                    buf = tail + block
                    hit = buf.find(_MARKER)
                    if hit >= 0:
                        at = consumed - len(tail) + hit
                        start = max(0, at - _BEFORE)
                        fh.seek(start)
                        slab = fh.read((at - start) + _AFTER)
                        return slab[: at - start], slab[at - start :]
                    consumed += len(block)
                    tail = buf[-overlap:] if overlap else b""
        except OSError:
            _log.debug("agent.model_discovery.binary_unreadable path=%s", path, exc_info=True)
            return None

    @staticmethod
    def _aliases(before: bytes) -> list[AgentModel]:
        """The tier aliases, in the order the bundle lists them. They carry no
        labels there and none are invented here: the id IS the word the CLI
        accepts on ``--model``, which is also the word the user recognises."""
        match = _ALIAS_RE.search(before)
        if match is None:
            return []
        out: list[AgentModel] = []
        for raw in _STRING_RE.findall(match.group(1)):
            alias = raw.decode("utf-8", "replace").strip()
            if alias:
                out.append(AgentModel(id=alias, source="alias"))
        return out

    @staticmethod
    def _catalog(after: bytes) -> list[AgentModel]:
        """The versioned entries, REVERSED.

        This is not a real sort — nothing here parses version numbers. The
        bundle happens to list each family oldest-first, so reversing puts the
        recent releases at the top of the picker, which is where a user looks
        first. If a future release orders the table differently the picker is
        merely ordered oddly; nothing breaks.
        """
        out: list[AgentModel] = []
        for model_id, display, cutoff in _ENTRY_RE.findall(after):
            ident = model_id.decode("utf-8", "replace").strip()
            if not ident:
                continue
            label = display.decode("utf-8", "replace").strip()
            known_to = cutoff.decode("utf-8", "replace").strip()
            out.append(
                AgentModel(
                    id=ident,
                    label=label,
                    # The only per-model prose the bundle carries. Rendered as a
                    # sentence because a bare date reads as noise in a picker.
                    description=f"Knowledge cutoff {known_to}" if known_to else "",
                    source="discovered",
                )
            )
        out.reverse()
        return out


__all__ = ["ClaudeBinaryModelDiscovery"]
