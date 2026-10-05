"""The page on the source's host that shows what changed between two commits.

Spec skill-manager "Hand a Git-imported skill's update to an agent": Coffer
draws no diff of its own; for GitHub and GitLab it links to the host's compare
page. Any other host has none, and the page shows the commit range instead.
The link is built from the repository's host and path only, so a credential in
the source URL never reaches it.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_SCP_RE = re.compile(r"^(?:[A-Za-z0-9._-]+@)?(?P<host>[A-Za-z0-9.-]+):(?P<path>[^/].*)$")
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
_SAFE_COMMIT_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _host_and_path(url: str) -> tuple[str, str] | None:
    """The repository's host and ``owner/repo`` path, for an ``https``,
    ``ssh://`` or ``git@host:path`` URL; ``None`` for anything else."""
    if "://" in url:
        parts = urlsplit(url)
        if parts.scheme.lower() not in ("https", "ssh") or not parts.hostname:
            return None
        host, path = parts.hostname.lower(), parts.path
    else:
        m = _SCP_RE.match(url.strip())
        if m is None:
            return None
        host, path = m.group("host").lower(), m.group("path")
    path = path.strip("/")
    path = path.removesuffix(".git").strip("/")
    return (host, path) if _SAFE_PATH_RE.match(path) else None


def compare_url(source_url: str, pinned: str, new: str) -> str | None:
    """The compare page from ``pinned`` to ``new``, or ``None`` when the host is
    neither GitHub nor GitLab (``gitlab.com`` or a host named ``gitlab.…``)."""
    found = _host_and_path(source_url)
    if found is None or not (_SAFE_COMMIT_RE.match(pinned) and _SAFE_COMMIT_RE.match(new)):
        return None
    host, path = found
    if host == "github.com":
        return f"https://github.com/{path}/compare/{pinned}...{new}"
    if host == "gitlab.com" or host.startswith("gitlab."):
        return f"https://{host}/{path}/-/compare/{pinned}...{new}"
    return None


__all__ = ["compare_url"]
