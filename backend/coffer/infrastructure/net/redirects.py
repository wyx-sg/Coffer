"""The one rule for redirects on a request that carries a secret.

Spec secret "Send a secret only to the origin it was approved for": a secret is
approved for a target (a URL, a bot), so a 3xx that points somewhere else must
not carry it there. ``httpx`` strips only ``Authorization`` on a cross-origin
redirect; ``X-API-Key``, ``api-key`` and a key in the query would follow, and
the OpenAI and Anthropic SDKs build clients that follow redirects by default.

The rule: **a client that sends a secret does not follow redirects.** The 3xx
comes back as the answer (the caller reports it, as the custom-tool runner does
with "Location: … (not followed)"). The one exception is the MCP SDK's own
transport, which follows only within the endpoint's origin by itself
(``mcp.shared._httpx_utils.stream_within_origin``). A test scans the package so
a new client cannot quietly break the rule.

This module is where the clients that need an explicit switch get it.
"""

from __future__ import annotations

from typing import Any

import httpx


def no_redirect_client(**kwargs: Any) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` that never follows a redirect."""
    kwargs["follow_redirects"] = False
    return httpx.AsyncClient(**kwargs)


def stop_following_redirects(client: Any) -> None:
    """Switch redirects off on an SDK client whose own default follows them.

    ``client`` is the ``httpx`` client inside an OpenAI or Anthropic SDK client
    (``follow_redirects`` is a plain attribute of ``httpx.Client``).
    """
    client.follow_redirects = False


__all__ = ["no_redirect_client", "stop_following_redirects"]
