"""Shared test helpers for ``backend/tests/integration/surfaces/http/``.

``client`` boots the full FastAPI app (via ``create_app``) so knowledge
routes are wired exactly as production wires them — real SQLite, real
markdown files under a temp HOME, the real converter registry — then drives
them with a Starlette ``TestClient`` (an ``httpx.Client`` subclass). It pins
``COFFER_KNOWLEDGE_ROOT`` and ``COFFER_INDEX_ROOT`` (the FR-025 disposable
sidecar) into ``tmp_path``, so no test here ever touches a real ``~/.coffer``.
Shared here — rather than duplicated per module — because both
``test_knowledge_search_ingest_routes.py`` and ``test_knowledge_search_ranking.py``
need the identical app wiring.

``FakeEmbedder`` stands in for the real embedder ``SearchService`` gets from
the internal connection (spec knowledge FR-026). The three ranked-retrieval
scenarios in ``test_knowledge_search_ranking.py`` need to control exactly
which vector a piece of text produces — a real embedding model would make
those tests both non-deterministic and dependent on network access neither
this suite nor CI has. ``FakeEmbedder`` is deterministic and explicit
instead: a fixed mapping from a known substring to a known vector.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

import pytest
from starlette.testclient import TestClient

from coffer.application.engine_ports import EmbedderPort
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-knowledge-search-ingest"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    # The ranked-retrieval sidecar (FR-025) — pinned so a test never touches a
    # real ~/.coffer/index.
    monkeypatch.setenv("COFFER_INDEX_ROOT", str(tmp_path / "index"))

    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        yield c


def _create_collection(client: TestClient, name: str) -> None:
    resp = client.post("/api/v1/knowledge/collections", json={"name": name})
    assert resp.status_code == 201, resp.text


def _write_file(
    client: TestClient, *, directory: str, title: str, description: str, body: str
) -> str:
    resp = client.put(
        "/api/v1/knowledge/file",
        json={"title": title, "description": description, "body": body, "directory": directory},
    )
    assert resp.status_code == 200, resp.text
    path: str = resp.json()["path"]
    return path


#: Returned for any text that matches none of a ``FakeEmbedder``'s mapped
#: substrings, unless the caller overrides it. Cosine similarity against a
#: zero-magnitude vector is defined as ``0.0`` by
#: ``coffer.domain.knowledge.retrieval.cosine`` (never a raise), which is
#: below ``DEFAULT_MIN_SCORE`` — so unmapped text reads as "unrelated to
#: every query" rather than as an accidental match.
DEFAULT_VECTOR: tuple[float, ...] = (0.0, 0.0, 0.0)


class FakeEmbedder:
    """Deterministic stand-in for :class:`EmbedderPort`.

    ``embed`` checks each input text against ``mapping`` in insertion order
    and returns the vector for the first key that appears as a substring of
    that text. A text matching no key gets ``default``. No randomness, no
    network, no real model — the same text always yields the same vector.
    """

    def __init__(
        self,
        mapping: dict[str, tuple[float, ...]],
        *,
        default: tuple[float, ...] = DEFAULT_VECTOR,
    ) -> None:
        self._mapping = mapping
        self._default = default

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._vector_for(text) for text in texts)

    def _vector_for(self, text: str) -> tuple[float, ...]:
        for key, vector in self._mapping.items():
            if key in text:
                return vector
        return self._default


def embedder_factory(
    embedder: FakeEmbedder | EmbedderPort | None,
) -> Callable[[], Awaitable[EmbedderPort | None]]:
    """Wrap a (possibly ``None``) embedder as a ``SearchService`` ``EmbedderFactory``.

    ``SearchService`` resolves its embedder fresh per call (the user may
    change the internal connection without a restart) — this just gives
    tests a fixed answer to resolve to, including "no connection configured"
    when ``embedder`` is ``None``.
    """

    async def factory() -> EmbedderPort | None:
        return embedder

    return factory
