"""Read what a model response cost from a copy of its bytes (ADR
api-key-providers-are-reached-through-a-separate-local-model-proxy, "Relay").

The model proxy relays every byte unchanged and feeds a COPY to one of the
readers here, beside the relay. Everything in this module is therefore pure
and incremental: it is handed chunks exactly as they came off the socket —
split anywhere, mid-line or mid-UTF-8 sequence — and it never raises into its
caller for a malformed stream (the relay also guards the call, but a reader
that raised on every odd upstream would turn a metering gap into noise).

Two wires, two readers, one output shape (:class:`StreamUsage`):

- **Anthropic Messages.** ``message_start.message.usage`` carries the input
  side; ``message_delta.usage`` carries the cumulative ``output_tokens`` and
  may RESTATE or EXTEND the input and cache totals (a server tool runs several
  sampling iterations and the final delta holds the grown numbers). The rule
  is: the last value seen per field wins, so ``message_delta`` overrides
  ``message_start``. Pricing the ``message_start`` breakdown and ignoring the
  larger final total is exactly how LiteLLM under-billed cache writes (#42663).
- **OpenAI Responses.** Usage arrives once, on the terminal
  ``response.completed`` / ``response.incomplete`` / ``response.failed``.
  OpenAI's ``input_tokens`` INCLUDES ``input_tokens_details.cached_tokens``;
  Anthropic's excludes cache reads. The record stores disjoint categories
  (:mod:`coffer.domain.usage.records`), so the cached part is subtracted here,
  once, and nowhere else. GPT-5.6 and later also report
  ``input_tokens_details.cache_write_tokens`` (also part of ``input_tokens``);
  it is subtracted the same way and recorded as a five-minute cache write.

A stream cut before its terminal event has unknown usage: :meth:`usage`
returns ``None`` and the record says ``usage_known = False`` — recorded,
never guessed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NamedTuple


class SseEvent(NamedTuple):
    """One dispatched server-sent event: its ``event:`` name and joined data."""

    event: str
    data: str


class SseParser:
    """An incremental ``text/event-stream`` parser (WHATWG event-stream rules).

    ``feed`` takes raw bytes in whatever pieces the socket delivered and returns
    the events those bytes completed. Lines end in ``\\n``, ``\\r\\n`` or a
    lone ``\\r``; a ``\\r`` that ends a chunk is held back, because the next
    chunk may begin with the ``\\n`` that makes it one line ending, not two.
    Comment lines (``:`` — Anthropic's and proxies' keep-alive pings) and
    unknown fields are skipped; several ``data:`` lines join with ``\\n``.
    """

    def __init__(self) -> None:
        self._buffer = b""
        self._event = ""
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[SseEvent]:
        self._buffer += chunk
        events: list[SseEvent] = []
        while True:
            line, found = self._next_line()
            if not found:
                return events
            event = self._line(line)
            if event is not None:
                events.append(event)

    def _next_line(self) -> tuple[bytes, bool]:
        buf = self._buffer
        lf = buf.find(b"\n")
        cr = buf.find(b"\r")
        if cr >= 0 and (lf < 0 or cr < lf):
            if cr == len(buf) - 1:
                return b"", False  # maybe the first half of \r\n: wait for more
            end = cr + 2 if buf[cr + 1 : cr + 2] == b"\n" else cr + 1
            line = buf[:cr]
        elif lf >= 0:
            end = lf + 1
            line = buf[:lf]
        else:
            return b"", False
        self._buffer = buf[end:]
        return line, True

    def _line(self, raw: bytes) -> SseEvent | None:
        if not raw:
            if not self._data and not self._event:
                return None
            event = SseEvent(self._event or "message", "\n".join(self._data))
            self._event, self._data = "", []
            return event
        text = raw.decode("utf-8", errors="replace")
        if text.startswith(":"):
            return None
        name, sep, value = text.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if name == "event":
            self._event = value
        elif name == "data":
            self._data.append(value)
        return None


@dataclass(frozen=True)
class StreamUsage:
    """Token counts in the record's disjoint categories.

    ``None`` means the wire does not report that category at all; a category
    the wire reports but left out of this response is ``0``.
    """

    input_tokens: int | None = None
    cache_write_5m_tokens: int | None = None
    cache_write_1h_tokens: int | None = None
    cache_read_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    web_search_requests: int | None = None
    speed: str | None = None
    inference_geo: str | None = None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _json_object(text: str | bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


class _Reader:
    """What both readers share: SSE framing and the three commit-point flags."""

    def __init__(self) -> None:
        self._sse = SseParser()
        self.saw_terminal = False
        self.saw_error_event = False
        self.first_content_seen = False

    def feed(self, chunk: bytes) -> None:
        for event in self._sse.feed(chunk):
            data = _json_object(event.data) if event.data else None
            self._on_event(event.event, data or {})

    def _on_event(self, name: str, data: dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError

    def read_json(self, body: bytes) -> None:  # pragma: no cover
        raise NotImplementedError

    def usage(self) -> StreamUsage | None:  # pragma: no cover
        raise NotImplementedError


class AnthropicUsageReader(_Reader):
    """Usage of one Anthropic Messages response, streamed or not."""

    _INT_FIELDS = (
        "input_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "output_tokens",
    )

    def __init__(self) -> None:
        super().__init__()
        self._fields: dict[str, Any] = {}
        self._usage_seen = False

    def _merge(self, usage: Any) -> None:
        """Last value per field wins — what makes ``message_delta`` override
        ``message_start``, and a later iteration's total replace an earlier one."""
        if not isinstance(usage, dict):
            return
        self._usage_seen = True
        for key in self._INT_FIELDS:
            value = _int(usage.get(key))
            if value is not None:
                self._fields[key] = value
        breakdown = usage.get("cache_creation")
        if isinstance(breakdown, dict):
            for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"):
                value = _int(breakdown.get(key))
                if value is not None:
                    self._fields[key] = value
        server = usage.get("server_tool_use")
        if isinstance(server, dict):
            value = _int(server.get("web_search_requests"))
            if value is not None:
                self._fields["web_search_requests"] = value
        for key in ("speed", "inference_geo"):
            text = usage.get(key)
            if isinstance(text, str):
                self._fields[key] = text

    def _on_event(self, name: str, data: dict[str, Any]) -> None:
        kind = data.get("type") or name
        if kind == "message_start":
            message = data.get("message")
            if isinstance(message, dict):
                self._merge(message.get("usage"))
        elif kind == "message_delta":
            self._merge(data.get("usage"))
        elif kind == "content_block_start":
            self.first_content_seen = True
        elif kind == "message_stop":
            self.saw_terminal = True
        elif kind == "error" or name == "error":
            self.saw_error_event = True

    def read_json(self, body: bytes) -> None:
        """A non-streamed response: one ``message`` object (or an ``error``)."""
        payload = _json_object(body)
        if payload is None:
            return
        if payload.get("type") == "error":
            self.saw_error_event = True
            return
        if "usage" in payload:
            self._merge(payload.get("usage"))
            self.first_content_seen = True
            self.saw_terminal = True

    def usage(self) -> StreamUsage | None:
        if not (self.saw_terminal and self._usage_seen):
            return None
        f = self._fields
        total_write = f.get("cache_creation_input_tokens")
        write_5m = f.get("ephemeral_5m_input_tokens", 0)
        write_1h = f.get("ephemeral_1h_input_tokens", 0)
        # The breakdown and the total can come from different events. Whatever
        # part of the (last) total the (last) breakdown does not account for is
        # a write at the default five-minute TTL — so a bare total counts as 5m,
        # and a final total larger than message_start's breakdown is never lost.
        if total_write is not None and total_write > write_5m + write_1h:
            write_5m += total_write - (write_5m + write_1h)
        return StreamUsage(
            input_tokens=f.get("input_tokens", 0),
            cache_write_5m_tokens=write_5m,
            cache_write_1h_tokens=write_1h,
            cache_read_tokens=f.get("cache_read_input_tokens", 0),
            output_tokens=f.get("output_tokens", 0),
            reasoning_tokens=None,
            web_search_requests=f.get("web_search_requests", 0),
            speed=f.get("speed"),
            inference_geo=f.get("inference_geo"),
        )


_RESPONSES_TERMINAL = frozenset({"response.completed", "response.incomplete", "response.failed"})
_RESPONSES_TERMINAL_STATUS = frozenset({"completed", "incomplete", "failed"})


class ResponsesUsageReader(_Reader):
    """Usage of one OpenAI Responses response, streamed or not."""

    def __init__(self) -> None:
        super().__init__()
        self._usage: dict[str, Any] | None = None

    def _take(self, response: Any) -> None:
        if isinstance(response, dict) and isinstance(response.get("usage"), dict):
            self._usage = response["usage"]

    def _on_event(self, name: str, data: dict[str, Any]) -> None:
        kind = data.get("type") or name
        if not isinstance(kind, str):
            return
        if kind in _RESPONSES_TERMINAL:
            self.saw_terminal = True
            self._take(data.get("response"))
            if kind == "response.failed":
                self.saw_error_event = True
        elif kind == "error":
            self.saw_error_event = True
        elif kind == "response.output_item.added" or kind.endswith(".delta"):
            self.first_content_seen = True

    def read_json(self, body: bytes) -> None:
        """A non-streamed response: one ``response`` object (or an ``error``)."""
        payload = _json_object(body)
        if payload is None:
            return
        if payload.get("object") != "response" and payload.get("error"):
            self.saw_error_event = True
            return
        status = payload.get("status")
        if status in _RESPONSES_TERMINAL_STATUS or "usage" in payload:
            self.saw_terminal = True
            self.first_content_seen = True
            self._take(payload)
            if status == "failed":
                self.saw_error_event = True

    def usage(self) -> StreamUsage | None:
        if not self.saw_terminal or self._usage is None:
            return None
        u = self._usage
        total_in = _int(u.get("input_tokens")) or 0
        details = u.get("input_tokens_details")
        cached = _int(details.get("cached_tokens")) if isinstance(details, dict) else None
        cached = min(cached or 0, total_in)
        # GPT-5.6 and later also report cache WRITES (charged above input);
        # like cached tokens they are part of ``input_tokens``. Responses has no
        # TTL split, so a write counts in the default five-minute bucket.
        written = _int(details.get("cache_write_tokens")) if isinstance(details, dict) else None
        written = min(max(written or 0, 0), total_in - cached)
        out_details = u.get("output_tokens_details")
        reasoning = (
            _int(out_details.get("reasoning_tokens")) if isinstance(out_details, dict) else None
        )
        return StreamUsage(
            input_tokens=total_in - cached - written,
            cache_write_5m_tokens=written,
            cache_write_1h_tokens=0,
            cache_read_tokens=cached,
            output_tokens=_int(u.get("output_tokens")) or 0,
            reasoning_tokens=reasoning or 0,
        )


UsageReader = AnthropicUsageReader | ResponsesUsageReader

__all__ = [
    "AnthropicUsageReader",
    "ResponsesUsageReader",
    "SseEvent",
    "SseParser",
    "StreamUsage",
    "UsageReader",
]
