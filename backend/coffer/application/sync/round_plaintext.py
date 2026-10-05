"""The check before every push (spec vault-sync "Refuse to push a plaintext secret").

A push publishes more than the files as they are now: it publishes every
file version in every commit the remote lacks. So the check reads each blob
reachable from the commit being pushed and not from the remote's head, with
the detector the Secrets page's scan uses (spec secret "Detect plaintext secrets
with the bundled rules"), and skips what is not plaintext:
an encrypted ``secret/<ref>.enc`` file, a binary file, and a blob the person
already said to push anyway.

Three outcomes:

* **nothing found** — the push goes ahead;
* **a file still holds a value** at the commit being pushed — the round stops
  as ``plaintext_found`` before pushing anything, naming each file, line and
  key (never the value);
* **only an earlier, unpushed commit holds it** — the file was fixed since,
  but pushing the commits as they are would still publish the value. The
  round folds the unpushed commits into one commit on the remote's head, with
  the same files, and pushes that. The vault's content does not change; only
  the per-commit history of those unpushed edits is merged into one entry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from coffer.application.sync.round_deps import RoundDeps
from coffer.domain.sync.handoffs import is_secret_file
from coffer.domain.sync.plaintext import PlaintextFinding
from coffer.domain.sync.rounds import RoundRecord, RoundStatus
from coffer.domain.vault.errors import VaultFileStale

#: Larger blobs are not text a person wrote by hand; they are not read.
MAX_BYTES = 1_000_000


@dataclass(frozen=True)
class PushCheck:
    #: The commit to push: the one asked about, or the folded one.
    commit: str
    #: Non-empty: stop the round, push nothing.
    findings: tuple[PlaintextFinding, ...] = ()
    #: How many unpushed commits were folded into ``commit``.
    folded: int = 0
    #: The vault moved while folding: the next round retries.
    moved: bool = False


def _text(raw: bytes | None) -> str | None:
    if raw is None or len(raw) > MAX_BYTES or b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def findings(d: RoundDeps, tip: str | None, final: str) -> tuple[PlaintextFinding, ...]:
    """Every plaintext value in what pushing ``final`` over ``tip`` publishes."""
    if d.find_plaintext is None:
        return ()
    allowed = d.state.plaintext_allowed()
    pairs = [
        (path, blob)
        for path, blob in d.git.new_blobs(tip, final)
        if not is_secret_file(path) and blob not in allowed
    ]
    if not pairs:
        return ()
    data = d.git.blobs([blob for _, blob in pairs])
    now = d.git.files(final)
    out: list[PlaintextFinding] = []
    for path, blob in pairs:
        text = _text(data.get(blob))
        if text is None:
            continue
        for line, key, rule in d.find_plaintext(text, path):
            out.append(
                PlaintextFinding(path, line, key, blob, current=now.get(path) == blob, rule=rule)
            )
    return tuple(sorted(out, key=lambda f: (not f.current, f.path, f.line)))


def check(d: RoundDeps, tip: str | None, final: str) -> PushCheck:
    """What to push instead of ``final``, or why nothing may be pushed."""
    found = findings(d, tip, final)
    if not found:
        return PushCheck(final)
    if any(f.current for f in found):
        return PushCheck(final, findings=found)
    return _fold(d, tip, final)


def _fold(d: RoundDeps, tip: str | None, final: str) -> PushCheck:
    """One commit on ``tip`` with ``final``'s files, checked out in its place."""
    with d.writer.lock:
        if d.git.head() != final:
            return PushCheck(final, moved=True)
        n = len(d.git.commits_between(tip, final))
        folded = d.git.commit_tree(
            d.git.tree_of(final),
            (tip,) if tip else (),
            d.sync_meta(f"Folded {n} unpushed commits so a removed plaintext value is not pushed"),
        )
        try:
            d.git.checkout(final, folded)
        except VaultFileStale:
            return PushCheck(final, moved=True)
    return PushCheck(folded, folded=n)


def refused(rec: Callable[..., RoundRecord], checked: PushCheck, **fields: Any) -> RoundRecord:
    """The record of a round that pushed nothing: a plaintext secret in what
    it would publish, or the vault moved while folding."""
    if checked.moved:
        return rec(
            RoundStatus.WAITING_ON_EDIT,
            detail="the vault changed during the round; the next round retries",
            **fields,
        )
    files = sorted({f.path for f in checked.findings if f.current})
    more = f" and {len(files) - 3} more" if len(files) > 3 else ""
    return rec(
        RoundStatus.PLAINTEXT_FOUND,
        plaintext=checked.findings,
        detail=f"a plaintext secret in {', '.join(files[:3])}{more}; nothing was pushed",
        **fields,
    )


__all__ = ["MAX_BYTES", "PushCheck", "check", "findings", "refused"]
