"""Everything git's three-way merge could not settle (spec vault-sync ``## Conflicts``).

Three layers, narrowest first, and the narrowness is the design:

1. **Credential blobs never reach a text merge.** A Fernet token carries its
   encryption time in cleartext, so two ciphertexts for one ref can be ordered
   without the key. The fresher encryption wins. This applies to
   ``credentials/*.enc`` and to nothing else — a general "newest wins" resolver
   is what the previous design's auto-resolve grew into, and it grew bugs with
   it.
2. **Delete-versus-edit over the file trees resolves toward the edit.** One
   side removed a document the other changed. The edit is something a person or
   an agent just decided; the deletion is a housekeeping judgement — the tidy
   pass merging a note away — that the next pass will simply make again. Losing
   the edit is unrecoverable, losing the deletion costs one more pass, so the
   asymmetry decides it (spec vault-sync "Let an edit beat a tidy deletion").
3. **An agent may attempt the rest**, when an internal model is configured. It
   works in the working tree only, never against the live vault, and it is not
   trusted: everything it touched goes through the validation gate below before
   the round treats it as an ordinary merge result.
4. **Otherwise the round stops** and the user resolves in their own git. This
   is the designed fallback, not an error path, which is why an unavailable
   resolver reports rather than raises.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import yaml

from coffer.application.sync.ports import ConflictResolverPort, GitMirrorPort
from coffer.domain.sync.fernet_time import is_fresher

_logger = logging.getLogger(__name__)

_CREDENTIALS = "credentials/"
_RESOURCES = "resources/"
_STATE = "state/"
#: The file trees, where a deletion is housekeeping and an edit is a decision.
#: Deliberately not ``resources/``: a deleted registration that keeps coming
#: back because someone touched its YAML is a worse failure than a lost edit.
_TREES = ("knowledge/", "skills/")
_OURS = ":2"
_THEIRS = ":3"
#: git writes these into a conflicted file; one surviving means the resolver
#: left the conflict in place while claiming it had not.
_MARKERS = (b"<<<<<<<", b"=======", b">>>>>>>")


class ConflictArbiter:
    """Resolves what it can and reports what it cannot."""

    def __init__(self, resolver: ConflictResolverPort) -> None:
        self._resolver = resolver

    async def arbitrate(
        self, mirror: GitMirrorPort, paths: Sequence[str]
    ) -> tuple[list[str], list[str]]:
        """Returns ``(resolved_by_agent, unresolved)``.

        Credential blobs settled by encryption time are deliberately absent
        from the first list: they were decided by a rule, not by a model, and
        the user is told about agent resolutions specifically because those are
        the ones worth reviewing.
        """
        remaining: list[str] = []
        for path in paths:
            if path.startswith(_CREDENTIALS) and await self._settle_credential(mirror, path):
                continue
            if path.startswith(_TREES) and await self._settle_delete_vs_edit(mirror, path):
                continue
            remaining.append(path)
        if not remaining:
            return [], []

        if not await self._resolver.available():
            return [], remaining

        try:
            claimed = await self._resolver.resolve(remaining)
        except Exception as e:  # a resolver failure is a fallback, not a crash
            _logger.warning("converge: conflict resolver failed: %s", e)
            return [], remaining

        resolved: list[str] = []
        for path in remaining:
            if path in claimed and await self._passes_gate(mirror, path):
                resolved.append(path)
        unresolved = [p for p in remaining if p not in resolved]
        return resolved, unresolved

    async def _settle_credential(self, mirror: GitMirrorPort, path: str) -> bool:
        """Take whichever side was encrypted later.

        A blob whose header will not parse leaves the path unsettled rather
        than guessing: the 2026-07-10 clobber happened precisely because a
        rule that could not really order two secrets picked one anyway.
        """
        ours = await mirror.read_file(_OURS, path)
        theirs = await mirror.read_file(_THEIRS, path)
        if ours is None or theirs is None:
            # One side deleted the credential. That is a real decision about
            # the vault, not an encryption race; let it reach the next layer.
            return False
        side = "theirs" if is_fresher(theirs, ours) else "ours"
        if side == "ours" and not is_fresher(ours, theirs) and ours != theirs:
            # Neither header ordered them. Refuse rather than pick.
            return False
        await mirror.take_side(path, side)
        return True

    async def _settle_delete_vs_edit(self, mirror: GitMirrorPort, path: str) -> bool:
        """Keep the edit when one side deleted what the other changed.

        Only for a delete/modify conflict, which git shows as a missing merge
        stage: exactly one of ours and theirs is absent. A conflict where both
        sides still hold the document is an ordinary content disagreement and
        goes on to the next layer — this rule is about a rewriter's deletion
        colliding with a decision, not about two people disagreeing.
        """
        ours = await mirror.read_file(_OURS, path)
        theirs = await mirror.read_file(_THEIRS, path)
        if (ours is None) == (theirs is None):
            return False
        await mirror.take_side(path, "ours" if ours is not None else "theirs")
        return True

    async def _passes_gate(self, mirror: GitMirrorPort, path: str) -> bool:
        """Whether a resolver's output may be treated as an ordinary merge.

        Three checks, in the order that fails cheapest: the file exists, it
        carries no conflict marker, and — for a document with a schema — it
        parses. A resolver that produced something unparseable has produced a
        document that would fail to apply anyway, and failing here keeps that
        out of the vault's history entirely.
        """
        content = await mirror.read_worktree(path)
        if content is None:
            return False
        if any(marker in content for marker in _MARKERS):
            return False
        if path.startswith((_RESOURCES, _STATE)):
            try:
                parsed = yaml.safe_load(content.decode("utf-8"))
            except (yaml.YAMLError, UnicodeDecodeError):
                return False
            if not isinstance(parsed, dict):
                return False
        return True
