"""What kind of thing a mounted link points at (spec workflow "Name what a
mounted external reference points at").

A run's inputs are LISTED to a node, never pasted in ("List a run's mounted
inputs to every node") — so a link is an address the node has to go and read for
itself. "Go and read it" is not one operation: a Confluence page is read with
the Confluence tool, a Jira issue with the Jira tool, an ordinary page by
fetching it. A node handed a bare URL has to guess which, and a wrong guess is a
failed tool call the developer sees as the run stalling.

So the provider is named when it can be recognised, and NOT named when it
cannot. A `web` fallback would be a guess wearing a label; ``None`` says "this
is a URL and nothing more is known about it", which is the truth and is what
lets a node fall back to fetching without believing it was told something.

Recognition is on the HOST, and on the path only where a host serves more than
one product — Atlassian Cloud puts Confluence and Jira on the same domain, and
Google puts Docs, Sheets and Slides on theirs. Self-hosted installations
(`confluence.example.com`, `jira.internal`) are recognised by the leading
label, because that is the convention every one of them follows and a
mis-recognition costs a wrong tool rather than anything unsafe.

This module makes no network calls and has no configuration: it is a pure
function from a string to a label, so it can run on a link mounted a year ago
and improve as the table grows. Nothing is stored — the provider is derived
every time a link is read, which is why an old run benefits from a new entry
here without a migration.
"""

from __future__ import annotations

from urllib.parse import urlparse

__all__ = ["LINK_PROVIDERS", "classify_link"]

#: The providers this module can name. Kept as a tuple so a caller can present
#: them (a UI label per provider) without importing the matching rules.
LINK_PROVIDERS = (
    "confluence",
    "jira",
    "google_docs",
    "google_sheets",
    "google_slides",
    "google_drive",
    "github",
    "gitlab",
    "figma",
    "notion",
    "slack",
)

#: Hosts that serve exactly one product, matched by suffix so a subdomain of
#: them counts (`mycorp.atlassian.net` is handled below, not here).
_HOST_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("github.com", "github"),
    ("gitlab.com", "gitlab"),
    ("figma.com", "figma"),
    ("notion.so", "notion"),
    ("notion.site", "notion"),
    ("slack.com", "slack"),
    ("docs.google.com", "google_docs"),
    ("drive.google.com", "google_drive"),
)

#: Google puts several products on `docs.google.com`, told apart by the first
#: path segment: `/document/…`, `/spreadsheets/…`, `/presentation/…`.
_GOOGLE_BY_SEGMENT = {
    "document": "google_docs",
    "spreadsheets": "google_sheets",
    "presentation": "google_slides",
    "forms": "google_docs",
}

#: Atlassian Cloud serves both products from one host; the path says which.
_ATLASSIAN_BY_SEGMENT = {
    "wiki": "confluence",
    "browse": "jira",
    "jira": "jira",
    "issues": "jira",
    "confluence": "confluence",
}

#: A self-hosted installation is named after the product it runs, which is the
#: convention every one of them follows.
_SELF_HOSTED_LABELS = {
    "confluence": "confluence",
    "wiki": "confluence",
    "jira": "jira",
}


def classify_link(url: str) -> str | None:
    """The provider ``url`` points at, or ``None`` when it is just a URL.

    ``None`` is a real answer and not a failure: it tells a node that nothing
    is known beyond the address, which is what lets it fetch the page rather
    than reach for a tool that was never going to work.
    """
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    first = segments[0].lower() if segments else ""

    if host == "docs.google.com":
        return _GOOGLE_BY_SEGMENT.get(first, "google_docs")

    for suffix, provider in _HOST_SUFFIXES:
        if host == suffix or host.endswith(f".{suffix}"):
            return provider

    if host.endswith(".atlassian.net"):
        return _ATLASSIAN_BY_SEGMENT.get(first, "confluence")

    # `confluence.example.com`, `jira.internal` — the leading label names the
    # product. Checked last so a host that matched something exact above is
    # never overruled by a coincidence in its first label.
    return _SELF_HOSTED_LABELS.get(host.split(".")[0])
