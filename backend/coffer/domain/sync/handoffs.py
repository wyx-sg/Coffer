"""The sync chores Coffer hands to the person's agent (spec vault-sync
"Hand a conflict's merge to an agent", "Hand a remote's failure to an agent").

Two chores depend on judgement or on the machine rather than on anything
Coffer can decide:

* **merging a conflicting file.** Coffer offers two manual answers (keep this
  machine's, take the other's) and a marked-up copy to edit. Merging the two
  edits is a chore for an agent. The agent edits only the marked-up copies
  Coffer wrote outside the vault, never the vault's files and never git. The
  person then records the merge with **I merged it** and continues the round,
  the way a skill update's merge is recorded.
* **a remote that refuses the round.** A rejected push, a sign-in the remote
  refused, or a remote that cannot be reached are fixed on the remote's side
  or on this machine's network, never by Coffer.
* **a plaintext secret in what the round would push.** Moving each value into
  a Coffer secret and pointing the file at it depends on the file (a
  resource's field, a skill's script), so the agent does it, without ever
  printing the value (spec vault-sync "Refuse to push a plaintext secret").

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
from coffer.domain.sync.plaintext import PlaintextFinding
from coffer.domain.sync.stops import ConflictFile, ConflictReason
from coffer.domain.vault.layout import SECRET

#: The conflict reasons whose file an agent can merge by editing it. Two
#: resources claiming one name, one uid at two paths, or a file changed on
#: one side and deleted on the other are decisions, not merges.
MERGEABLE_REASONS = frozenset({ConflictReason.BOTH_CHANGED, ConflictReason.INVALID_MERGE})

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
    both sides edited it (or the merge git made is not a valid document)."""
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
    """One file handed to the agent, and where each side last changed it."""

    conflict: ConflictFile
    #: The marked-up copy the agent edits (outside the vault).
    copy: str
    #: The newest commit touching the file on this machine's side and on the
    #: other side (``None``: none found).
    ours_commit: str | None = None
    theirs_commit: str | None = None


def _short(commit: str | None) -> str:
    return commit[:7] if commit else "unknown"


def conflict_merge_handoff(
    *,
    vault: str,
    machine: str,
    local: str,
    remote: str,
    base: str | None,
    files: Sequence[MergeFile],
    secret_files: int = 0,
) -> str | None:
    """The prompt that asks an agent to merge a stopped round's files, or
    ``None`` when none of them is the agent's to merge."""
    if not files:
        return None
    other = next((f.conflict.theirs_machine for f in files if f.conflict.theirs_machine), None)
    other = other or "the other machine"
    facts: list[str] = [
        f"The vault (a git repository Coffer commits to): {vault}",
        f"This machine: {machine}; the other side: {other}.",
        f"This machine's commit: {local}; the other side's commit: {remote}; "
        f"their merge base: {base or 'none (no common history)'}.",
    ]
    for f in files[:_MAX_FILES]:
        c = f.conflict
        facts.append(
            f"{c.path}: changed here in {_short(f.ours_commit)}"
            + (f" at {c.ours_time}" if c.ours_time else "")
            + f", and on {c.theirs_machine or other} in {_short(f.theirs_commit)}"
            + (f" at {c.theirs_time}" if c.theirs_time else "")
            + f". Marked-up copy to edit: {f.copy}"
        )
    more = len(files) - _MAX_FILES
    if more > 0:
        facts.append(f"And {more} more files; `coffer sync conflicts` lists every one.")
    if secret_files:
        noun = "file is" if secret_files == 1 else "files are"
        facts.append(
            f"{secret_files} encrypted secret {noun} in conflict too. Leave them alone: "
            "I choose a side for them in Coffer."
        )
    diff_from = base or local
    see = (
        f"See what each side changed with `git -C {vault} diff {diff_from} {local} -- <path>` "
        f"(this machine) and `git -C {vault} diff {diff_from} {remote} -- <path>` "
        f"({other}); `git -C {vault} show {remote}:<path>` prints the other side's whole file."
        if base
        else f"See how the two sides differ with `git -C {vault} diff {local} {remote} -- <path>`; "
        f"`git -C {vault} show {remote}:<path>` prints the other side's whole file."
    )
    return render_handoff(
        Handoff(
            task=(
                f"A Coffer sync round stopped on {len(files)} "
                + ("file" if len(files) == 1 else "files")
                + f" that both this machine and {other} changed. Merge each file's two versions "
                "in the marked-up copy Coffer prepared."
            ),
            facts=tuple(facts),
            steps=(
                see,
                "Only read the vault: run no git command that changes it (commit, merge, "
                "checkout, reset, stash, push), and do not edit the vault's own files. "
                "Coffer commits the merged result itself.",
                "Edit only the marked-up copies listed above. Keep what each side meant; where "
                "the two really disagree, ask me. Remove every conflict marker "
                "(<<<<<<<, =======, >>>>>>>).",
                "When every copy is merged, show me what you changed and tell me it is ready. "
                "I finish it in Coffer with I merged it and Continue round (on the command "
                "line: `coffer sync resolve --merged`, then `coffer sync continue`); do not run "
                "them yourself.",
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


# --- a plaintext secret in what the round would push ----------------------------------------


def plaintext_handoff(*, vault: str, findings: Sequence[PlaintextFinding]) -> str | None:
    """The prompt to move each plaintext value the round found into a Coffer
    secret, or ``None`` when no file still holds one. Names the file, the line
    and the key; never the value."""
    current = [f for f in findings if f.current]
    if not current:
        return None
    facts = [f"The vault (a git repository Coffer commits to): {vault}"]
    for f in current[:_MAX_FILES]:
        what = "a value shaped like a token" if f.key == "token" else f"the value of {f.key}"
        facts.append(f"{f.path}, line {f.line}: {what}.")
    more = len(current) - _MAX_FILES
    if more > 0:
        facts.append(f"And {more} more; `coffer sync status` lists every one.")
    facts += [
        "`coffer secret set <name>` stores the value it reads on stdin as the secret <name>; "
        "a file then refers to it as coffer://secret/<name>, and `coffer run --secret "
        "ENV=<name> -- <command>` hands it to one command in the variable ENV.",
        "`coffer secret list` lists the secret names Coffer already holds, never their values.",
    ]
    return render_handoff(
        Handoff(
            task=(
                "Coffer did not push my vault to its sync remote: "
                + ("a file holds" if len(current) == 1 else f"{len(current)} places hold")
                + " what looks like a plaintext secret. Move each value into a Coffer secret "
                "and point the file at it, without ever showing the value."
            ),
            facts=tuple(facts),
            steps=(
                "Never print, echo, log, paste or repeat a value, and do not quote the line it "
                "is on. To store one, pipe it straight from the file into `coffer secret set "
                "<name>` (for example with a one-line script that writes only that value to "
                "the command's stdin), choosing a short lowercase name for it.",
                "Then replace the value in the file with coffer://secret/<name>. Where a "
                "skill's command needs the value itself, run that command through `coffer run "
                "--secret ENV=<name> -- …` instead.",
                "If a value is an example or a test value and not a real secret, leave it and "
                "tell me: I choose Push anyway in Coffer.",
                "Run no git command in the vault; Coffer commits your edits itself and does not "
                "publish the old value from its history. When every place is done, tell me and "
                "I press Retry in Coffer.",
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
    "plaintext_handoff",
    "remote_failure_handoff",
    "scrub_git_text",
]
