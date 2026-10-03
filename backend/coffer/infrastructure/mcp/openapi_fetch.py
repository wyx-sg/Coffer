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
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml

from coffer.domain.mcp.custom_tool_errors import (
    OpenApiUnreachable,
    OpenApiUnreadable,
    UnreachableReason,
)
from coffer.domain.mcp.http_api import HTTP_METHODS
from coffer.domain.mcp.openapi_import import OperationSource
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
        except json.JSONDecodeError as e:
            raise OpenApiUnreadable(
                f"the document is not valid JSON: {e.msg}", line=e.lineno, column=e.colno
            ) from e
        except ValueError as e:
            raise OpenApiUnreadable(f"the document is not valid JSON: {e}") from e
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark is not None else ""
        raise OpenApiUnreadable(
            f"the document is not valid YAML{where}",
            line=mark.line + 1 if mark is not None else None,
            column=mark.column + 1 if mark is not None else None,
        ) from e


#: The longest operation excerpt returned, in lines.
MAX_SNIPPET_LINES = 400


def locate_operations(text: str) -> dict[str, OperationSource]:
    """Where each ``"<METHOD> <path>"`` operation sits in ``text``.

    JSON is read as YAML (its subset), so one reader gives line numbers for
    both. A document that cannot be composed locates nothing."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return {}
    paths = _entry(root, "paths")
    if not isinstance(paths, yaml.MappingNode):
        return {}
    lines = text.splitlines()
    found: dict[str, OperationSource] = {}
    for path_key, item in paths.value:
        if not isinstance(item, yaml.MappingNode):
            continue
        for method_key, op in item.value:
            method = str(method_key.value).upper()
            if method not in HTTP_METHODS:
                continue
            start = method_key.start_mark.line + 1
            end = _last_line(lines, op.end_mark)
            end = min(max(end, start), start + MAX_SNIPPET_LINES - 1, len(lines))
            found[f"{method} {path_key.value}"] = OperationSource(
                start_line=start, end_line=end, text="\n".join(lines[start - 1 : end])
            )
    return found


def _last_line(lines: list[str], mark: yaml.Mark) -> int:
    """The 1-based line a node's text ends on. A block node's end mark sits at
    the start of whatever follows it, so when only indentation precedes the mark
    on its line the node ended on an earlier one."""
    index = mark.line
    if index >= len(lines):
        index = len(lines) - 1
    elif lines[index][: mark.column].strip() == "":
        index -= 1
    while index > 0 and not lines[index].strip():
        index -= 1
    return index + 1


def _entry(node: yaml.Node | None, key: str) -> yaml.Node | None:
    if not isinstance(node, yaml.MappingNode):
        return None
    return next((v for k, v in node.value if getattr(k, "value", None) == key), None)


def _resolves(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return True
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True


async def _guard(url: str) -> None:
    try:
        await asyncio.to_thread(check_url, url)
    except ValueError as e:
        # A name that does not resolve is a network failure, not a refused address.
        if not await asyncio.to_thread(_resolves, url):
            raise OpenApiUnreachable(url, "dns") from e
        raise OpenApiUnreadable(
            f"{e}. Coffer fetches an OpenAPI URL only from a public address; "
            "import a document on a private or local host as a file instead"
        ) from e


def _connect_reason(e: httpx.ConnectError) -> UnreachableReason:
    cause: BaseException | None = e
    while cause is not None:
        if isinstance(cause, socket.gaierror):
            return "dns"
        if isinstance(cause, ConnectionRefusedError):
            return "refused"
        cause = cause.__cause__ or cause.__context__
    return "unreachable"


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
                raise OpenApiUnreachable(url, "timeout") from e
            except httpx.ConnectError as e:
                raise OpenApiUnreachable(url, _connect_reason(e)) from e
            except httpx.HTTPError as e:
                raise OpenApiUnreadable(f"could not fetch the document: {type(e).__name__}") from e
    raise OpenApiUnreadable("the document's URL redirected too many times")


class OpenApiDocumentSource:
    """``application.mcp.custom_tool_ports.OpenApiSourcePort``."""

    async def fetch(self, url: str) -> tuple[str, str]:
        return await fetch_document(url)

    def parse(self, text: str) -> Any:
        return parse_document(text)

    def locate(self, text: str) -> dict[str, OperationSource]:
        return locate_operations(text)


__all__ = [
    "FETCH_TIMEOUT_SECONDS",
    "MAX_DOCUMENT_BYTES",
    "OpenApiDocumentSource",
    "fetch_document",
    "locate_operations",
    "parse_document",
]
