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

WHY THE RETIREMENT TABLE TOO. The catalog is cumulative — it keeps every model
the CLI has ever known, including ones the account can no longer run — so the
raw scan offers a picker full of names that fail the moment they are chosen.
The bundle carries the answer for a subset of them: a second table pairing a
model id with its per-provider retirement dates and, for the ones the CLI
silently reroutes, the tier it is remapped to. The CLI's own predicate treats a
model as gone when it carries a ``remappedTo`` or when its retirement date has
passed, and this source now applies exactly that predicate over ``firstParty``
— the column describing a direct Anthropic account, which is what Coffer's
users are on; Bedrock/Vertex/Foundry describe deployments Coffer does not
configure and whose dates differ. The clock is injected so the rule is testable
without writing a test that expires.

WHAT THIS DOES NOT DO. It does not answer "which models may THIS account run".
That is a server-provided account fact — the CLI gets it in its own config
payload, and nothing on disk holds it — so no local rule can derive it. Pricing,
capabilities, knowledge cutoffs and version numbers were all checked against a
known-good set and separate none of them. Curating the remainder is the user's
job (see ``AgentConfig.models``); all this table can do is keep the list they
curate from carrying models that are dead for everyone.

WHAT this costs when it breaks. The bundle's shapes are an implementation
detail of a release we do not control. If a future CLI renames a marker or
changes a literal layout, that anchor simply fails to match: a missing catalog
anchor returns nothing, and a missing retirement anchor returns the catalog
UNFILTERED rather than a filter built from half a table. It cannot return wrong
data, and it cannot fail a request.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import pathlib
import re
import shutil
from collections.abc import Callable
from typing import IO, NamedTuple

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

#: The retirement table has no comment above it, so the landmark is the shape of
#: its first entry's date block — a literal that appears nowhere else.
_RETIRE_MARKER = b"retirementDates:{firstParty:"

#: The marker lands INSIDE the first entry, so the window has to start before it
#: to catch that entry's own id. One entry is ~300 bytes; this is ample.
_RETIRE_BEFORE = 8 * 1024

#: The whole table was ~1.4 KB when this was written; a generous multiple.
_RETIRE_AFTER = 64 * 1024

#: Streaming scan block size — the bundle is far too large to read whole.
_BLOCK = 4 * 1024 * 1024

#: One catalog entry. ``family`` is not used in the output; it is here purely as
#: an anchor, so a bare ``{id:"…"}`` elsewhere in the bundle cannot match.
_ENTRY_RE = re.compile(
    rb'\{id:"(claude-[^"]+)",family:"[^"]+",display_name:"([^"]+)"'
    rb'(?:,knowledge_cutoff:"([^"]*)")?'
)

#: One retirement-table entry: the id, the ``firstParty`` date (or ``null``),
#: and whether a ``remappedTo`` follows the date block. ``[^{}]*`` is safe
#: because the date block carries no nested object.
_RETIRE_RE = re.compile(
    rb'"(claude-[^"]+)":\{modelName:"[^"]*",retirementDates:\{'
    rb'firstParty:(null|"[^"]+")[^{}]*\}(,remappedTo:)?'
)

#: Month names as the table spells them ("June 15, 2026"). Parsed by hand rather
#: than with ``strptime('%B …')``, whose month names follow the process locale —
#: a daemon started under a non-English locale would silently parse nothing.
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_DATE_RE = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")


class _Retirement(NamedTuple):
    """One row of the CLI's retirement table, kept unevaluated.

    The date is held as TEXT and compared per call rather than at scan time: the
    scan is cached for the life of an installed binary, and a retirement date
    can fall due while the daemon is running.
    """

    model_id: str
    first_party: str | None
    remapped: bool


def _parse_date(text: str) -> dt.date | None:
    """``"June 15, 2026"`` → a date; anything unrecognised → ``None`` (which
    this module reads as "no opinion", never as "retired")."""
    m = _DATE_RE.match(text.strip())
    if m is None:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    try:
        return dt.date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


class ClaudeBinaryModelDiscovery:
    """``ModelDiscoveryPort`` backed by the installed ``claude`` executable.

    Cached in-process on (resolved path, mtime, size): the scan touches a
    200 MB file, and the answer only changes when the CLI is upgraded — which
    replaces the symlink target, so the key changes with it. The retirement
    VERDICT is not cached — only the table it is computed from — so a date that
    falls due mid-session still takes effect.
    """

    def __init__(
        self,
        *,
        binary_name: str = "claude",
        today: Callable[[], dt.date] | None = None,
    ) -> None:
        self._binary_name = binary_name
        self._today = today or dt.date.today
        self._cache: tuple[tuple[str, int, int], list[AgentModel], tuple[_Retirement, ...]] | None
        self._cache = None

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        """The CLI's versioned catalog, minus the models it says are gone.

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
            _, models, retirements = self._cache
        else:
            models, retirements = self._scan(path)
            self._cache = (key, models, retirements)
        gone = self._gone(retirements)
        return [m for m in models if m.id not in gone]

    def _gone(self, retirements: tuple[_Retirement, ...]) -> frozenset[str]:
        """The CLI's own ``$J`` predicate: a model is gone when the CLI silently
        reroutes it (``remappedTo``) or when its first-party retirement date is
        in the past. An empty table means no opinion, so nothing is filtered."""
        today = self._today()
        out: set[str] = set()
        for entry in retirements:
            if entry.remapped:
                out.add(entry.model_id)
                continue
            if entry.first_party is None:
                continue
            retires = _parse_date(entry.first_party)
            if retires is not None and retires < today:
                out.add(entry.model_id)
        return frozenset(out)

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

    def _scan(self, path: pathlib.Path) -> tuple[list[AgentModel], tuple[_Retirement, ...]]:
        """One streaming pass for both landmarks, then the two slices they name.

        Both tables live in the same 200 MB file half a megabyte apart, so
        looking for them separately would read the bundle twice.
        """
        try:
            with path.open("rb") as fh:
                offsets = self._find_markers(fh, (_MARKER, _RETIRE_MARKER))
                catalog = self._slice(fh, offsets.get(_MARKER), before=0, after=_AFTER)
                table = self._slice(
                    fh,
                    offsets.get(_RETIRE_MARKER),
                    before=_RETIRE_BEFORE,
                    after=_RETIRE_AFTER,
                )
        except OSError:
            _log.debug("agent.model_discovery.binary_unreadable path=%s", path, exc_info=True)
            return [], ()
        if catalog is None:
            return [], ()
        return self._catalog(catalog), self._retirements(table)

    @staticmethod
    def _find_markers(fh: IO[bytes], markers: tuple[bytes, ...]) -> dict[bytes, int]:
        """Absolute offset of each marker's FIRST occurrence, in one pass.

        Consecutive blocks are stitched by an overlap of the longest marker so a
        landmark straddling a block boundary is still found. A marker that never
        appears is simply absent from the result.
        """
        overlap = max(len(m) for m in markers) - 1
        found: dict[bytes, int] = {}
        consumed = 0
        tail = b""
        while len(found) < len(markers):
            block = fh.read(_BLOCK)
            if not block:
                break
            buf = tail + block
            base = consumed - len(tail)
            for marker in markers:
                if marker in found:
                    continue
                hit = buf.find(marker)
                if hit >= 0:
                    found[marker] = base + hit
            consumed += len(block)
            tail = buf[-overlap:] if overlap else b""
        return found

    @staticmethod
    def _slice(fh: IO[bytes], offset: int | None, *, before: int, after: int) -> bytes | None:
        """The window around ``offset``; ``None`` when the marker was absent."""
        if offset is None:
            return None
        start = max(0, offset - before)
        fh.seek(start)
        return fh.read((offset - start) + after)

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

    @staticmethod
    def _retirements(window: bytes | None) -> tuple[_Retirement, ...]:
        """The retirement table as rows, or EMPTY when the anchor did not match.

        Empty means "no filter", which is the only safe failure: a table this
        module cannot read must cost the user a slightly longer list, never a
        model wrongly hidden.
        """
        if window is None:
            return ()
        rows: list[_Retirement] = []
        for model_id, date_text, remapped in _RETIRE_RE.findall(window):
            ident = model_id.decode("utf-8", "replace").strip()
            if not ident:
                continue
            raw = date_text.decode("utf-8", "replace")
            first_party = None if raw == "null" else raw.strip('"')
            rows.append(_Retirement(ident, first_party, bool(remapped)))
        return tuple(rows)


__all__ = ["ClaudeBinaryModelDiscovery"]
