"""Replace exact secret values in a byte stream with ``***``.

The accident guard of ``coffer run`` (ADR
standalone-secrets-are-named-references-injected-into-one-child, "Output
masking — accidental-leak defence only"). It catches a command that prints a
value it was given — a config dump, a verbose error — and nothing more: it
does not see a transformed value (base64, a substring), what the child writes
to a file, or what an agent reads from the child's environment. Values shorter
than :data:`MIN_MASKED_LENGTH` are not masked; masking a three-letter value
would shred ordinary output.

Streaming: a value split across two reads is still caught, because the tail
that could be the start of a value is held back until the next chunk.
"""

from __future__ import annotations

MIN_MASKED_LENGTH = 8
MASK = b"***"


class StreamMasker:
    def __init__(self, values: list[str]) -> None:
        encoded = {v.encode() for v in values if len(v) >= MIN_MASKED_LENGTH}
        # Longest first, so a value containing another is masked whole.
        self._values = sorted(encoded, key=len, reverse=True)
        self._hold = max((len(v) for v in self._values), default=1) - 1
        self._buffer = b""

    @property
    def active(self) -> bool:
        return bool(self._values)

    def _mask(self, data: bytes) -> bytes:
        for value in self._values:
            data = data.replace(value, MASK)
        return data

    def feed(self, chunk: bytes) -> bytes:
        """What may be written now; a possible value prefix waits for more."""
        if not self._values:
            return chunk
        data = self._mask(self._buffer + chunk)
        if self._hold <= 0 or len(data) <= self._hold:
            self._buffer = data if self._hold > 0 else b""
            return b"" if self._hold > 0 else data
        cut = len(data) - self._hold
        self._buffer = data[cut:]
        return data[:cut]

    def flush(self) -> bytes:
        data, self._buffer = self._mask(self._buffer), b""
        return data
