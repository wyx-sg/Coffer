"""Which connection Coffer transcribes speech with (spec internal-engine
"Transcribe speech on its own connection and model").

Transcription runs on the connection the operator MARKED ``transcribe_default``,
paired with a model chosen apart from it. Both halves are required, and a
missing one is an answer rather than a failure.

What the engine cannot know is which provider row carries the flag — and it
must not learn. Reaching into ``application.provider`` from here would hand
every consumer of the engine an indirect import of a kind it does not name, and
the cross-kind contracts would fail. So the provider kind answers that one
question through :class:`TranscribeConnectionPort`, which the composition root
satisfies.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Annotation-only: naming the provider kind's value object executes none of
    # its code, which is exactly what ``exclude_type_checking_imports`` exists
    # for. An import out here instead would re-form the chain described above.
    from coffer.domain.provider.config import ResolvedConnection


#: Reads the globally-chosen speech-to-text model, or ``None`` when the
#: operator has chosen none. Called per resolution rather than captured, so a
#: model chosen (or forgotten) after wiring takes effect at once.
InternalModelReader = Callable[[], Awaitable[str | None]]


class TranscribeConnectionPort(Protocol):
    """The one question the engine puts to the provider kind: which connection
    is marked ``transcribe_default``, paired with this model."""

    async def transcribe_connection(self, model: str) -> ResolvedConnection | None: ...


async def resolve_transcribe_connection(
    *,
    read_model: InternalModelReader,
    connections: TranscribeConnectionPort,
) -> ResolvedConnection | None:
    """The connection + model Coffer transcribes speech with, or ``None``.

    There is deliberately no fallback to another connection: the endpoint that
    serves chat completions commonly serves no ``/audio/transcriptions`` at all,
    so borrowing it would replace "Coffer transcribes nothing, and hands the
    agent the audio" — a state the chat surface already handles, and which keeps
    the recording on this machine — with a 404 on every voice message. An
    unmarked connection or an unchosen model is an answer.
    """
    model = await read_model()
    if not model:
        return None
    return await connections.transcribe_connection(model)


__all__ = [
    "InternalModelReader",
    "TranscribeConnectionPort",
    "resolve_transcribe_connection",
]
