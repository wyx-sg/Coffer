"""Drop the kept attention report around every write request.

The attention list is computed once and handed to every reader for a while
(:class:`~coffer.application.attention.AttentionService`). Most writes reach it
through the watcher's nudge, but not every action that resolves an item is a
resource write — approving a secret request, running a sync round, adopting a
skill. So any request that may write (anything but ``GET``, ``HEAD`` and
``OPTIONS``) drops the kept report when it starts and again when its response
starts: the page's refetch after the action, which follows the response, reads
the list as the action left it.

Pure ASGI rather than ``BaseHTTPMiddleware``: the event stream is a long-lived
streaming response, which must pass through untouched.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from coffer.surfaces.http import reconcile_dependencies

_READS = frozenset({"GET", "HEAD", "OPTIONS"})


def _invalidate() -> None:
    try:
        service = reconcile_dependencies.get_attention_service()
    except RuntimeError:
        return  # not wired yet (start-up) or in a test without it
    service.invalidate()


class AttentionFreshness:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET") in _READS:
            await self.app(scope, receive, send)
            return
        _invalidate()

        async def send_after(message: Message) -> None:
            if message["type"] == "http.response.start":
                _invalidate()
            await send(message)

        await self.app(scope, receive, send_after)


__all__ = ["AttentionFreshness"]
