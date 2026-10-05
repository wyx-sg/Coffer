"""The sync chores Coffer hands to the person's agent (spec vault-sync
"Hand conflicting files to an agent", "Hand a remote's failure to an agent").

Two chores depend on judgement or on the machine rather than on anything
Coffer can decide:

* **merging a conflicting file.** Coffer offers two manual answers (keep this
  machine's, take the other's) and a marked-up copy to edit. Merging the two
  edits is a chore for an agent. The agent writes only the marked-up copies
  Coffer prepared outside the vault, never the vault's files and never git.
  The person checks the merge in that copy and marks it resolved; an
  agent's merge is never an answer by itself.
* **a remote that refuses the round.** A rejected push, a sign-in the remote
  refused, or a remote that cannot be reached are fixed on the remote's side
  or on this machine's network, never by Coffer.

A plaintext secret in what the round would push is never handed to an agent:
the prompt would send it to the file that holds the value. The person moves it
into secrets on the Sync page (spec vault-sync "Refuse to push a plaintext
secret").

What a prompt never carries: a secret's value, a push token, a URL's user
name or password, or the contents of a ``secret/*.enc`` file. An encrypted
secret file is never merged by an agent; the person chooses a side for it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.sync.stops import ConflictFile, ConflictReason
from coffer.domain.vault.layout import SECRET

#: The conflict reasons whose file an agent can merge by editing it. Two
#: resources claiming one name, one uid at two paths, or a file changed on
#: one side and deleted on the other are decisions, not merges.
MERGEABLE_REASONS = frozenset(
    {ConflictReason.BOTH_CHANGED, ConflictReason.INVALID_MERGE, ConflictReason.JOIN_DIFFERS}
)

#: How many files a prompt lists; the rest are counted.
_MAX_FILES = 30

#: Token shapes git hosts issue, scrubbed from git's text before it is handed
#: over (the push token itself is already replaced where git's stderr is read).
_TOKENS = re.compile(
    r"\b(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|(?:glpat|glrt|gldt|glptt)-[A-Za-z0-9_\-]{16,})"
)
#: ``Authorization: …`` headers and ``Bearer``/``Basic`` credentials: the
#: scheme word is kept, what follows it is not.
_AUTH_HEADER = re.compile(r"(?i)\b(authorization:)[^\n]*")
_AUTH_VALUE = re.compile(r"(?i)\b(bearer|basic)(\s+)\S+")
#: ``scheme://user:password@host`` (or ``user@``) inside any text.
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s@]+@")


def is_secret_file(path: str) -> bool:
    """Whether ``path`` is an encrypted secret (``secret/<ref>.enc``)."""
    return path.startswith(SECRET + "/") and path.endswith(".enc")


def agent_mergeable(conflict: ConflictFile) -> bool:
    """Whether an agent may merge this file: never a secret, and only when
    both sides edited it (or the merge git made is not a valid document), or a
    join found it different on both sides."""
    return not is_secret_file(conflict.path) and conflict.reason in MERGEABLE_REASONS


def display_remote(url: str) -> str:
    """``url`` without any user name or password in it (an SSH ``git@host:``
    address names a login, not a credential, and is kept as it is)."""
    if "://" not in url:
        return url
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def scrub_git_text(text: str) -> str:
    """Git's message with URL credentials and anything shaped like a token
    replaced by ``***``."""
    out = _URL_USERINFO.sub(r"\1***@", text)
    out = _TOKENS.sub("***", out)
    out = _AUTH_HEADER.sub(r"\1 ***", out)
    return _AUTH_VALUE.sub(r"\1\2***", out)


# --- merging a conflict ----------------------------------------------------------


@dataclass(frozen=True)
class MergeFile:
    """One file handed to the agent, and where it writes the merge."""

    conflict: ConflictFile
    #: The marked-up copy the agent edits (outside the vault).
    copy: str


def conflict_merge_handoff(
    *,
    vault: str,
    machine: str,
    files: Sequence[MergeFile],
    secret_files: int = 0,
    joining: bool = False,
) -> str | None:
    """The prompt that asks an agent to merge the files two machines both
    changed (a stopped round's, or a first join's differing ones), or ``None``
    when none of them is the agent's to merge. It states the goal and the
    constraints only: how the agent reads the two versions is its own business."""
    if not files:
        return None
    other = next((f.conflict.theirs_machine for f in files if f.conflict.theirs_machine), None)
    other = other or "the other machine"
    facts: list[str] = [
        f"The vault (read it for context; do not edit its files): {vault}",
        f"This machine: {machine}; the other side: {other}.",
    ]
    for f in files[:_MAX_FILES]:
        c = f.conflict
        facts.append(
            f"{c.path}: "
            + (f"changed here at {c.ours_time}" if c.ours_time else "changed here")
            + f", and on {c.theirs_machine or other}"
            + (f" at {c.theirs_time}" if c.theirs_time else "")
            + f". Merged copy to write: {f.copy}"
        )
    more = len(files) - _MAX_FILES
    if more > 0:
        facts.append(f"And {more} more files, each with its own merged copy.")
    if secret_files:
        noun = "file is" if secret_files == 1 else "files are"
        facts.append(
            f"{secret_files} encrypted secret {noun} in conflict too. Leave them alone: "
            "I choose a side for them in Coffer."
        )
    one = len(files) == 1
    count = "One file" if one else f"{len(files)} files"
    what = ("differs" if one else "differ") if joining else ("was" if one else "were")
    return render_handoff(
        Handoff(
            task=(
                f"{count} {what} "
                + ("between" if joining else "changed on both")
                + f" this machine and {other}"
                + (" when it joined the sync remote" if joining else ", so Coffer's sync stopped")
                + ". Merge each file's two versions into one."
            ),
            facts=tuple(facts),
            steps=(
                "Each merged copy starts with both versions between conflict markers "
                "(<<<<<<<, =======, >>>>>>>): this machine's first, the other side's second.",
                "Write the merged result into that copy, replacing its whole content, with no "
                "marker left. Keep what each side added; where the two contradict, ask me "
                "which to keep before writing it.",
                "Edit only the merged copies listed above. Coffer writes the merged file into "
                "the vault when I mark it resolved, so leave the vault's own files and its git "
                "history alone.",
                "When every copy is merged, tell me which files you merged and what you decided "
                "where the sides differed. I check the result in Coffer.",
            ),
        )
    )


# --- a remote that refuses the round ----------------------------------------------------

#: What to check, by problem kind.
_CHECKS: dict[str, tuple[str, ...]] = {
    "push_failed": (
        "Read git's message: it names why the remote refused the push.",
        "If the branch is protected (a rule or hook that declines pushes), either allow "
        "pushes from this secret's key or token on that branch, or point Coffer at a branch "
        "it may push to.",
        "Check the secret Coffer pushes with has write access to the repository, not only "
        "read access (a read-only deploy key, or a token without the write scope).",
        "If the remote's branch was rewritten (a force-push), tell me before anything else: "
        "Coffer does not force-push, and the fix is a decision for me.",
    ),
    "auth_failed": (
        "Check the remote URL and branch are right and the repository still exists.",
        "Check how this machine authenticates to that host: for an SSH URL, whether the key "
        "Coffer uses is still registered with the host; for HTTPS, whether the token is still "
        "valid, has the repository's read and write scope, and is sent with the user name the "
        "host expects (GitLab: oauth2 or the account name).",
        "Do not ask me for the token or read it: if it needs replacing, tell me and I replace "
        "it in Coffer's Secrets myself.",
    ),
    "unreachable": (
        "Check whether this machine can reach the remote's host: DNS, the network, a VPN or "
        "proxy the host needs, or a firewall on the port (22 for SSH, 443 for HTTPS).",
        "If the host is down, say so; there is nothing to change on this machine.",
    ),
}

_TASKS = {
    "push_failed": "The Coffer sync remote refused this machine's push. Find out why and tell me "
    "how to fix it.",
    "auth_failed": "The Coffer sync remote refused to sign this machine in. Find out why and "
    "tell me how to fix it.",
    "unreachable": "Coffer cannot reach its sync remote from this machine. Find out why.",
}


def remote_failure_handoff(
    kind: str,
    *,
    url: str,
    branch: str,
    detail: str,
    secret_ref: str | None,
    username: str | None,
) -> str | None:
    """The prompt for a remote's failure, or ``None`` for a kind that has none."""
    checks = _CHECKS.get(kind)
    if checks is None:
        return None
    facts = [
        f"Remote: {display_remote(url)}",
        f"Branch: {branch}",
        "How Coffer signs in: "
        + (
            f"the secret named {secret_ref} in Coffer's Secrets (its value is not shared here)"
            if secret_ref
            else "no secret; git's own SSH setup on this machine"
        )
        + (f", sent with the user name {username}" if username and "://" in url else "")
        + ".",
        f"Git said: {scrub_git_text(detail).strip() or 'nothing'}",
    ]
    return render_handoff(
        Handoff(
            task=_TASKS[kind],
            facts=tuple(facts),
            steps=(
                *checks,
                "Change nothing in Coffer's vault folder, and do not push to the remote "
                "yourself. When it is fixed, tell me and I press Retry in Coffer.",
            ),
        )
    )


__all__ = [
    "MERGEABLE_REASONS",
    "MergeFile",
    "agent_mergeable",
    "conflict_merge_handoff",
    "display_remote",
    "is_secret_file",
    "remote_failure_handoff",
    "scrub_git_text",
]
