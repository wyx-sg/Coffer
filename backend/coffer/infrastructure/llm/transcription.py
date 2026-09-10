"""Remote speech-to-text over an OpenAI-compatible ``/audio/transcriptions``.

Coffer used to transcribe voice locally, bundling a ``whisper.cpp`` sidecar
built from source in CI (a decision since retired). That was the heaviest build
dependency in the project by a wide margin, for a feature a remote endpoint
does at least as well.

**This is the one place user content may leave the machine, and it is off by
default.** Nothing is uploaded unless the user has designated an
``internal_default`` connection — the same connection that already runs
knowledge merge, organize and reorg, so voice introduces no new concept and no
new place to configure. With no such connection, or one whose protocol has no
transcription endpoint, :func:`remote_transcriber` returns ``None`` and the
adapter hands the agent the audio file untouched, exactly as before.

The constitution permits this: cloud services are LLM and tool providers, and a
transcription endpoint is a tool provider. The audio is data in transit, not
vault state — the transcript lands locally like any other turn text.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Awaitable, Callable

import httpx

from coffer.domain.provider.config import Protocol, ResolvedConnection

_logger = logging.getLogger(__name__)

#: The de-facto name for the OpenAI-compatible transcription model. Gateways
#: that expose the endpoint under a different id can be pointed at it without a
#: release; the connection itself is chosen by the user.
_MODEL_ENV = "COFFER_TRANSCRIBE_MODEL"
_DEFAULT_MODEL = "whisper-1"

#: A voice message is short. A minute is generous for one and still bounds a
#: wedged endpoint well inside the turn's own patience.
_TIMEOUT_SECONDS = 60.0

#: Protocols whose wire format carries an OpenAI-compatible transcription
#: endpoint. ``anthropic`` has none. ``unknown`` is an endpoint the probe could
#: not classify, and is worth trying: a gateway that speaks OpenAI's shape is
#: the common case behind an inconclusive probe.
_TRANSCRIBING_PROTOCOLS = frozenset({Protocol.OPENAI, Protocol.UNKNOWN})


class RemoteTranscriber:
    """POSTs the audio file to ``<base_url>/audio/transcriptions``.

    Never raises to the caller: a failure returns ``""`` and the adapter falls
    back to handing the agent the audio file path.
    """

    def __init__(self, connection: ResolvedConnection, api_key: str | None) -> None:
        self._base_url = connection.config.base_url.rstrip("/")
        self._api_key = api_key
        self._model = os.environ.get(_MODEL_ENV, "").strip() or _DEFAULT_MODEL

    async def transcribe(self, path: str) -> str:
        try:
            audio = await _read_bytes(path)
        except OSError:
            _logger.warning("transcribe.unreadable", extra={"path": path}, exc_info=True)
            return ""
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers=headers,
                    files={"file": (pathlib.Path(path).name, audio)},
                    data={"model": self._model, "response_format": "json"},
                )
                resp.raise_for_status()
                body = resp.json()
        except Exception:
            _logger.warning("transcribe.failed", extra={"model": self._model}, exc_info=True)
            return ""
        text = body.get("text") if isinstance(body, dict) else None
        return str(text).strip() if text else ""


async def _read_bytes(path: str) -> bytes:
    import asyncio

    return await asyncio.to_thread(pathlib.Path(path).read_bytes)


def remote_transcriber(
    connection: ResolvedConnection | None,
    credential_resolver: Callable[[str], str],
) -> RemoteTranscriber | None:
    """Build a transcriber for ``connection``, or ``None`` to send nothing.

    ``None`` is the default answer and the safe one: no internal connection
    configured, a protocol with no transcription endpoint, or a credential that
    will not resolve all mean the audio stays on this machine.
    """
    if connection is None:
        return None
    if connection.config.protocol not in _TRANSCRIBING_PROTOCOLS:
        return None
    ref = connection.config.credential_ref
    key: str | None = None
    if ref is not None:
        try:
            key = credential_resolver(ref)
        except Exception:
            _logger.info("transcribe.credential_unresolved", extra={"ref": ref})
            return None
    return RemoteTranscriber(connection, key)


def remote_transcriber_factory(
    resolve_connection: Callable[[], Awaitable[ResolvedConnection | None]],
    credential_resolver: Callable[[str], str],
) -> Callable[[], Awaitable[RemoteTranscriber | None]]:
    """A per-turn factory: the connection is resolved when a turn needs it, so
    designating (or clearing) the internal default takes effect without a
    restart."""

    async def _build() -> RemoteTranscriber | None:
        try:
            connection = await resolve_connection()
        except Exception:
            _logger.info("transcribe.connection_unresolved", exc_info=True)
            return None
        return remote_transcriber(connection, credential_resolver)

    return _build


__all__ = ["RemoteTranscriber", "remote_transcriber", "remote_transcriber_factory"]
