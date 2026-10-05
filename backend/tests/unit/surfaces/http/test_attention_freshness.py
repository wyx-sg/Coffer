"""A request that may write drops the kept attention report; a read does not."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from coffer.surfaces.http import reconcile_dependencies
from coffer.surfaces.http.attention_freshness import AttentionFreshness


class _Attention:
    def __init__(self) -> None:
        self.invalidated = 0

    def invalidate(self) -> None:
        self.invalidated += 1


@pytest.fixture
def attention() -> Iterator[_Attention]:
    fake = _Attention()
    reconcile_dependencies.set_attention_service(fake)  # type: ignore[arg-type]
    yield fake
    reconcile_dependencies.set_attention_service(None)


def _client() -> TestClient:
    async def ok(_request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", ok, methods=["GET", "POST", "PUT", "DELETE"])])
    app.add_middleware(AttentionFreshness)
    return TestClient(app)


def test_a_write_drops_the_report_before_and_after(attention: _Attention) -> None:
    client = _client()
    for method in ("POST", "PUT", "DELETE"):
        attention.invalidated = 0
        assert client.request(method, "/x").status_code == 200
        assert attention.invalidated == 2


def test_a_read_keeps_it(attention: _Attention) -> None:
    client = _client()
    client.get("/x")
    client.head("/x")
    assert attention.invalidated == 0


def test_nothing_to_drop_before_the_service_is_wired() -> None:
    reconcile_dependencies.set_attention_service(None)
    assert _client().post("/x").status_code == 200
