"""``ClaudeBinaryModelDiscovery`` — read Claude Code's model list out of its own
compiled binary.

WHY this exists at all. The CLI has no ``list models`` command and no local API
that answers "what can I run?", so the only machine-readable copy of that answer
on this machine is the one the CLI itself was built with. It ships as a single
bun-compiled executable that embeds a hand-maintained catalog, marked in the
bundle by a literal comment. Coffer reads that rather than writing the names
down, because a written-down list goes stale and — more importantly — cannot
tell two releases of the same tier apart. The catalog carries the version in
every display name; that is the whole point of reading it.

WHY ONLY the catalog. The bundle also carries the tier-alias array the
``--model`` flag accepts (``sonnet``, ``opus``, ``best``, ``sonnet[1m]``,
``opusplan``, …), and this source used to emit those alongside the catalog. It
no longer does. Every alias resolves to a model the catalog already lists, so
emitting both padded the picker with nine label-less entries sitting next to the
real models they point at. The CLI itself treats them as pointers, not models —
it strips a trailing ``[1m]`` before comparing two model names, so ``sonnet[1m]``
and ``sonnet`` are the same model to it, differing only in a context-window
flag. Nothing becomes unreachable: ``/model <name>`` and the agent's own config
still accept any alias string, and the CLI validates it. The cost, accepted
knowingly: ``best`` and ``opusplan`` are routing BEHAVIOURS rather than single
models, so after this they can only be set by typing the name, not by picking
one from a list. That is a decision, not an oversight.

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

#: How much of the bundle to keep from the marker on. The catalog entries run a
#: fair way past it; this is a generous multiple of what was observed.
_AFTER = 128 * 1024

#: Streaming scan block size — the bundle is far too large to read whole.
_BLOCK = 4 * 1024 * 1024

#: One catalog entry. ``family`` is not used in the output; it is here purely as
#: an anchor, so a bare ``{id:"…"}`` elsewhere in the bundle cannot match.
_ENTRY_RE = re.compile(
    rb'\{id:"(claude-[^"]+)",family:"[^"]+",display_name:"([^"]+)"'
    rb'(?:,knowledge_cutoff:"([^"]*)")?'
)


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
        """The CLI's versioned catalog.

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
        return self._catalog(window)

    @staticmethod
    def _read_window(path: pathlib.Path) -> bytes | None:
        """Stream the bundle looking for the marker, then re-read the slice that
        starts at it. ``None`` if the marker is absent."""
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
                        fh.seek(consumed - len(tail) + hit)
                        return fh.read(_AFTER)
                    consumed += len(block)
                    tail = buf[-overlap:] if overlap else b""
        except OSError:
            _log.debug("agent.model_discovery.binary_unreadable path=%s", path, exc_info=True)
            return None

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
                )
            )
        out.reverse()
        return out


__all__ = ["ClaudeBinaryModelDiscovery"]
