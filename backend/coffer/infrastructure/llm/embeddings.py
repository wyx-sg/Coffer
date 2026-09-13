"""Remote text embeddings over an OpenAI-compatible ``/embeddings`` endpoint.

Coffer's knowledge layer used to keep its own embedding settings — a
provider, a model, an endpoint, a key — a second place to stand up a second
provider, and the table sat empty because nobody did (spec knowledge,
background). This client asks for none of that: it POSTs to whichever
connection the user has already marked ``internal_default`` for Coffer's
internal engine, the same connection that already runs knowledge merge,
organize and reorg, so a fresh install with nothing configured beyond that
connection gets ranked retrieval for free (FR-026).

With no such connection, or one whose protocol carries no OpenAI-compatible
embeddings endpoint, :func:`remote_embedder` returns ``None`` and the caller
(the index builder) degrades to the literal/regex search FR-027 requires —
never an error, never emptiness for that reason alone. The index itself is a
disposable sidecar (FR-025): a failed or missing embedder just means fewer
files get a vector this pass, not a broken installation.

One divergence from this module's template, ``transcription.py``: that module
excludes ``ollama`` (a hosted, hand-transcribed-audio endpoint most local
model servers don't run). Here ``ollama`` IS included — it already speaks the
OpenAI wire at the same ``/v1`` base URL this codebase gives it (see
``provider_introspector.py``'s ``ollama`` entry), and it is precisely the
loopback, internal-only connection this feature is built to ride: the case
where "no second provider to configure" matters most.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

import httpx

from coffer.domain.provider.config import Protocol, ResolvedConnection

_logger = logging.getLogger(__name__)

#: Env override in the same style as transcription's ``COFFER_TRANSCRIBE_MODEL``.
#: Not a user setting (there is deliberately no settings surface for this layer,
#: FR-026): every vector in the disposable index must come from the same model,
#: since similarity across two models' vector spaces is meaningless — so the
#: model is an internal-engine implementation detail, pinned in code and
#: adjustable only by whoever operates the install, not by a form the index
#: would then need to invalidate itself against.
_MODEL_ENV = "COFFER_EMBED_MODEL"
_DEFAULT_MODEL = "text-embedding-3-small"

#: Indexing a corpus runs in the background, not on a user's turn, so it can
#: afford to wait — but a wedged endpoint must not hang a request forever.
#: 30s is generous for a batch of short knowledge-file excerpts while still
#: bounding the wait to well inside a background job's own patience.
_TIMEOUT_SECONDS = 30.0

#: OpenAI's ``input`` field accepts an array, so a whole batch goes in one
#: request. 64 keeps a single request's body small (short knowledge-file
#: excerpts, not whole documents) and comfortably under gateways' own
#: request-size or array-length caps, while still amortizing per-request
#: overhead across the "hundreds of files" corpus the spec assumes.
_BATCH_SIZE = 64

#: Protocols whose wire format carries an OpenAI-compatible embeddings
#: endpoint. ``anthropic`` has none. ``unknown`` is an endpoint the probe
#: could not classify, and is worth trying: a gateway that speaks OpenAI's
#: shape is the common case behind an inconclusive probe. ``ollama`` is
#: included — see the module docstring for why it differs from
#: ``transcription.py``'s precedent.
_EMBEDDING_PROTOCOLS = frozenset({Protocol.OPENAI, Protocol.OLLAMA, Protocol.UNKNOWN})


class RemoteEmbedder:
    """POSTs to ``<base_url>/embeddings`` (OpenAI-compatible).

    Never raises to the caller: any failure — transport error, non-2xx, a
    malformed body, or a vector count that doesn't match the input — returns
    an empty tuple and logs a warning. Callers treat ``()`` as "ranking
    unavailable, fall back to literal search".
    """

    def __init__(self, connection: ResolvedConnection, api_key: str | None) -> None:
        self._base_url = connection.config.base_url.rstrip("/")
        self._api_key = api_key
        self._model = os.environ.get(_MODEL_ENV, "").strip() or _DEFAULT_MODEL

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        vectors: list[tuple[float, ...]] = []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                for start in range(0, len(texts), _BATCH_SIZE):
                    batch = list(texts[start : start + _BATCH_SIZE])
                    resp = await client.post(
                        f"{self._base_url}/embeddings",
                        headers=headers,
                        json={"model": self._model, "input": batch},
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    vectors.extend(_parse_vectors(body, len(batch)))
        except Exception:
            # A failure in any batch fails the whole call: a partial index is
            # worse than none, since a caller can't tell a short result from a
            # merely-smaller-than-expected corpus.
            _logger.warning(
                "embed.failed", extra={"model": self._model, "count": len(texts)}, exc_info=True
            )
            return ()
        return tuple(vectors)


def _parse_vectors(body: Any, expected: int) -> list[tuple[float, ...]]:
    """Extract ``expected`` vectors from an OpenAI-shaped ``/embeddings`` body.

    Raises ``ValueError`` on any shape the caller can't trust; ``embed``
    treats that identically to a transport failure.
    """
    if not isinstance(body, dict):
        raise ValueError("response body is not a JSON object")
    data = body.get("data")
    if not isinstance(data, list) or len(data) != expected:
        got = len(data) if isinstance(data, list) else type(data).__name__
        raise ValueError(f"expected {expected} embeddings, got {got}")
    # OpenAI returns entries in request order tagged with an `index`; sort by
    # it when every entry carries one, so a gateway that reorders a batch
    # doesn't silently misalign a vector to the wrong text.
    if all(isinstance(entry, dict) and isinstance(entry.get("index"), int) for entry in data):
        data = sorted(data, key=lambda entry: entry["index"])
    vectors: list[tuple[float, ...]] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("embedding entry is not an object")
        embedding = entry.get("embedding")
        if (
            not isinstance(embedding, list)
            or not embedding
            or not all(isinstance(x, int | float) for x in embedding)
        ):
            raise ValueError("embedding is not a non-empty numeric array")
        vectors.append(tuple(float(x) for x in embedding))
    return vectors


def remote_embedder(
    connection: ResolvedConnection | None, api_key: str | None
) -> RemoteEmbedder | None:
    """Build an embedder for ``connection``, or ``None`` to embed nothing.

    ``None`` is the default answer and the safe one: no internal connection
    configured, or one whose protocol has no embeddings endpoint, both mean
    the index builder falls back to literal search rather than failing.
    """
    if connection is None:
        return None
    if connection.config.protocol not in _EMBEDDING_PROTOCOLS:
        return None
    return RemoteEmbedder(connection, api_key)


__all__ = ["RemoteEmbedder", "remote_embedder"]
