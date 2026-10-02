"""What a person typed as a skill's Git source, made into one location.

A repository URL, an optional ref and an optional subpath (spec skill-manager
"Add skills from a Git repository"). A GitHub folder address —
``https://github.com/<owner>/<repo>/tree/<ref>/<path>`` — carries all three,
so it is read as them when the ref and the path were not given separately; a
ref containing ``/`` cannot be told apart from the path there, so only its
first segment is taken as the ref.

The URL itself is checked only for what would make git misread it: an option
(a leading ``-``), a transport git would run a program for (``ext::``), or no
recognisable transport at all. Whether the host answers is git's to say.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

#: The transports a skill source may use; ``GIT_ALLOW_PROTOCOL`` pins the same.
ALLOWED_SCHEMES = ("https", "http", "ssh", "git", "file")
_SCP_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^/].*$")
_GITHUB_TREE_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)(?:/(?P<path>.+?))?/?$"
)
_REF_RE = re.compile(r"^[A-Za-z0-9._/@+-]{1,200}$")


class GitLocationError(ValueError):
    """The typed source cannot name a repository location."""


@dataclass(frozen=True)
class GitLocation:
    url: str
    ref: str | None
    subpath: str


def normalise_subpath(path: str | None) -> str:
    """A repository-relative folder: POSIX, no leading or trailing ``/``, no ``..``."""
    if not path:
        return ""
    parts = [p for p in path.strip().replace("\\", "/").split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise GitLocationError(f"the path {path!r} leaves the repository")
    return "/".join(parts)


def parse_git_location(url: str, ref: str | None = None, path: str | None = None) -> GitLocation:
    """Read ``url`` (plus an explicit ref / path) as one repository location."""
    url = url.strip().strip("\"'")
    ref = (ref or "").strip() or None
    if not url or url.startswith("-"):
        raise GitLocationError("a repository URL is required")
    m = _GITHUB_TREE_RE.match(url)
    if m is not None:
        url = f"https://github.com/{m.group('owner')}/{m.group('repo')}"
        ref = ref or m.group("ref")
        path = path or m.group("path")
    if "://" in url:
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise GitLocationError(f"the {scheme!r} transport is not allowed for a skill source")
        _refuse_credentials(url, scheme)
    elif not _SCP_RE.match(url):
        raise GitLocationError(f"{url!r} is not a repository URL")
    if ref is not None and (ref.startswith("-") or not _REF_RE.match(ref)):
        raise GitLocationError(f"{ref!r} is not a branch, tag or commit")
    return GitLocation(url=url, ref=ref, subpath=normalise_subpath(path))


def _refuse_credentials(url: str, scheme: str) -> None:
    """A source URL is stored in the vault (which syncs), in the skill's own
    metadata and in API answers, so it carries no credential: the git
    credential helper or an ssh key supplies one. ``ssh://git@host/…`` keeps its
    user name — that is an account, not a secret — but a password never stays."""
    parts = urlsplit(url)
    if parts.password is not None or (parts.username and scheme != "ssh"):
        raise GitLocationError(
            "the repository URL must not carry a user name or password; "
            "let git's credential helper or an ssh key supply it"
        )


def display_url(url: str) -> str:
    """``url`` without any user name or password it carries, for messages."""
    if "://" not in url:
        return url
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


__all__ = [
    "ALLOWED_SCHEMES",
    "GitLocation",
    "GitLocationError",
    "display_url",
    "normalise_subpath",
    "parse_git_location",
]
