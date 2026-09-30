"""Fetch and parse an OpenAPI document for import (design add-http-custom-tools §4, §8).

A URL typed into the import form is fetched **on the user's behalf**, so it
passes the SSRF guard first, and so does every redirect it answers with
(Principles → Network defaults; spec mcp-gateway "Import custom tools from an
OpenAPI document"). A spec on a private host is imported as a file instead.
The document is capped at 5 MiB and the whole fetch at 20 seconds.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml

from coffer.domain.mcp.custom_tool_errors import OpenApiUnreadable
from coffer.infrastructure.net.ssrf_guard import check_url

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 20.0
_MAX_REDIRECTS = 3


def parse_document(text: str) -> Any:
    """JSON, else YAML. Raises ``OpenApiUnreadable`` naming where it broke."""
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise OpenApiUnreadable("the document is larger than 5 MiB")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return json.loads(text)
        except ValueError as e:
            raise OpenApiUnreadable(f"the document is not valid JSON: {e}") from e
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark is not None else ""
        raise OpenApiUnreadable(f"the document is not valid YAML{where}") from e


async def _guard(url: str) -> None:
    try:
        await asyncio.to_thread(check_url, url)
    except ValueError as e:
        raise OpenApiUnreadable(
            f"{e}. Coffer fetches an OpenAPI URL only from a public address; "
            "import a document on a private or local host as a file instead"
        ) from e


async def fetch_document(url: str) -> tuple[str, str]:
    """``(final URL, text)`` of the document at ``url``."""
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            await _guard(current)
            try:
                async with client.stream("GET", current) as response:
                    if response.is_redirect and "location" in response.headers:
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        raise OpenApiUnreadable(
                            f"fetching the document answered HTTP {response.status_code}"
                        )
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_DOCUMENT_BYTES:
                            raise OpenApiUnreadable("the document is larger than 5 MiB")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    return current, raw.decode(response.encoding or "utf-8", errors="replace")
            except httpx.TimeoutException as e:
                raise OpenApiUnreadable("fetching the document timed out") from e
            except httpx.HTTPError as e:
                raise OpenApiUnreadable(f"could not fetch the document: {type(e).__name__}") from e
    raise OpenApiUnreadable("the document's URL redirected too many times")


class OpenApiDocumentSource:
    """``application.mcp.custom_tool_ports.OpenApiSourcePort``."""

    async def fetch(self, url: str) -> tuple[str, str]:
        return await fetch_document(url)

    def parse(self, text: str) -> Any:
        return parse_document(text)


__all__ = [
    "FETCH_TIMEOUT_SECONDS",
    "MAX_DOCUMENT_BYTES",
    "OpenApiDocumentSource",
    "fetch_document",
    "parse_document",
]
