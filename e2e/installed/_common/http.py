"""One HTTP client to the target daemon, with a redacted transcript of every exchange."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from e2e.installed._common.redact import Redactor
from e2e.installed._common.target import Target

ACTOR = "qa-installed-acceptance"


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: Any
    elapsed_ms: float

    @property
    def json(self) -> dict[str, Any]:
        """The body when it is a JSON object, else ``{}`` (so lookups stay simple)."""
        return self.body if isinstance(self.body, dict) else {}


class DaemonClient:
    """Speaks to the target with its token; never follows a redirect or reads proxies."""

    def __init__(self, target: Target, redactor: Redactor, transcript: Path) -> None:
        self.target = target
        self._redactor = redactor
        self._transcript = transcript
        self._http = httpx.AsyncClient(
            base_url=target.base_url, trust_env=False, follow_redirects=False, timeout=15
        )

    def headers(self, extra: Mapping[str, str | None] | None = None) -> dict[str, str]:
        """The default headers merged with ``extra``; a ``None`` value drops a header."""
        merged: dict[str, str | None] = {
            "X-Coffer-Token": self.target.token,
            "X-Coffer-Actor": ACTOR,
            "Accept": "application/json, text/event-stream",
        }
        merged.update(extra or {})
        return {k: v for k, v in merged.items() if v is not None}

    def log(self, entry: dict[str, Any]) -> None:
        entry = {"time": datetime.now(UTC).isoformat(), **entry}
        with self._transcript.open("a") as out:
            out.write(json.dumps(self._redactor.value(entry), default=str) + "\n")

    async def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        headers: Mapping[str, str | None] | None = None,
        content: bytes | str | None = None,
        timeout: float = 15,
    ) -> Reply:
        sent = self.headers(headers)
        start = time.perf_counter()
        kwargs: dict[str, Any] = {"headers": sent, "timeout": timeout}
        if content is not None:
            kwargs["content"] = content
        elif body is not None:
            kwargs["json"] = body
        response = await self._http.request(method, path, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        try:
            parsed: Any = response.json()
        except ValueError:
            parsed = response.text
        reply = Reply(response.status_code, dict(response.headers), parsed, elapsed)
        self.log(
            {
                "direction": "request",
                "method": method,
                "path": path,
                "request": body if content is None else str(content)[:2000],
                "request_headers": sent,
                "status": reply.status,
                "response_headers": reply.headers,
                "response": _clip(parsed),
                "elapsed_ms": round(elapsed, 1),
            }
        )
        return reply

    @asynccontextmanager
    async def stream(
        self, method: str, path: str, *, headers: Mapping[str, str | None], timeout: float
    ) -> AsyncIterator[httpx.Response]:
        async with self._http.stream(
            method, path, headers=self.headers(headers), timeout=timeout
        ) as response:
            self.log(
                {
                    "direction": "stream-open",
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "response_headers": dict(response.headers),
                }
            )
            yield response

    async def aclose(self) -> None:
        await self._http.aclose()


def _clip(value: Any, limit: int = 20000) -> Any:
    """Keep the transcript readable: a huge body is kept as its head and its size."""
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return value
    return {"clipped_bytes": len(text), "head": text[:limit]}
