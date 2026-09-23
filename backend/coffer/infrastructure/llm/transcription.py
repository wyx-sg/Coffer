"""Remote speech-to-text over an OpenAI-compatible ``/audio/transcriptions``.

Transcription is remote because a local engine would be this project's
heaviest build dependency by a wide margin, for a feature a remote endpoint
does at least as well.

**This is the one place user content may leave the machine, and it is off by
default.** Nothing is uploaded unless the user has designated a
``transcribe_default`` connection AND chosen a model for it. With neither, one
of the two, or a protocol that has no transcription endpoint,
:func:`remote_transcriber` returns ``None`` and the adapter hands the agent
the audio file untouched.

**Its own connection, with no fallback to the engine's.** Speech-to-text used to
borrow the ``internal_default`` connection on the reasoning that voice should
introduce no new place to configure. It introduced a worse one: the gateway a
user points Coffer's engine at commonly serves chat completions and no
``/audio/transcriptions`` at all, so the borrowed connection turned every voice
message into a 404 — where a connection deliberately left unset produces the
safe behaviour above. The model was an environment variable on top of that, read
inside a daemon spawned detached from any shell, which made it unreachable in a
packaged install. Both are settings now (spec internal-engine "Transcribe speech
on its own connection and model").

Principle I in ``docs/principles.md`` permits this: cloud services are LLM and tool providers, and a
transcription endpoint is a tool provider. The audio is data in transit, not
vault state — the transcript lands locally like any other turn text.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Awaitable, Callable

import httpx

from coffer.application.engine_timeout import (
    DEFAULT_MODEL_TIMEOUT_S,
    TimeoutReader,
    resolve_timeout,
)
from coffer.domain.provider.config import Protocol, ResolvedConnection

_logger = logging.getLogger(__name__)

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

    def __init__(
        self,
        connection: ResolvedConnection,
        api_key: str | None,
        timeout: float = DEFAULT_MODEL_TIMEOUT_S,
    ) -> None:
        self._base_url = connection.config.base_url.rstrip("/")
        self._api_key = api_key
        # The model travels ON the resolved connection, the same way the
        # engine's does: both halves are chosen by the operator and neither
        # has a default worth guessing.
        self._model = connection.model
        self._timeout = timeout

    async def transcribe(self, path: str) -> str:
        try:
            audio = await _read_bytes(path)
        except OSError:
            _logger.warning("transcribe.unreadable", extra={"path": path}, exc_info=True)
            return ""
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
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
    timeout: float = DEFAULT_MODEL_TIMEOUT_S,
) -> RemoteTranscriber | None:
    """Build a transcriber for ``connection``, or ``None`` to send nothing.

    ``None`` is the default answer and the safe one: no connection marked for
    transcription, no model chosen for it, a protocol with no transcription
    endpoint, or a credential that will not resolve all mean the audio stays
    on this machine.
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
    return RemoteTranscriber(connection, key, timeout)


def remote_transcriber_factory(
    resolve_connection: Callable[[], Awaitable[ResolvedConnection | None]],
    credential_resolver: Callable[[str], str],
    read_timeout: TimeoutReader | None = None,
) -> Callable[[], Awaitable[RemoteTranscriber | None]]:
    """A per-turn factory: the connection is resolved when a turn needs it, so
    designating (or clearing) it takes effect without a restart."""

    async def _build() -> RemoteTranscriber | None:
        try:
            connection = await resolve_connection()
        except Exception:
            _logger.info("transcribe.connection_unresolved", exc_info=True)
            return None
        return remote_transcriber(
            connection, credential_resolver, await resolve_timeout(read_timeout)
        )

    return _build


__all__ = ["RemoteTranscriber", "remote_transcriber", "remote_transcriber_factory"]
