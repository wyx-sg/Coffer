"""Interpret the ``openclaw agent --json`` result blob for the chat adapter.

Pure mapping over one parsed JSON object — openclaw is NON-STREAMING: the whole
turn arrives as a single blob on process exit, so unlike the line-delimited
mappers (opencode/cursor) there is no per-event state machine. The blob shape
(captured from a live ``openclaw agent --json --local`` run, openclaw
2026.6.11):

- ``payloads``: top-level list of ``{"text": …}`` chunks — the reply the user
  sees;
- ``meta.finalAssistantVisibleText``: the same reply flattened (fallback
  source);
- ``meta.stopReason`` and ``meta.completion.finishReason``: why the model
  stopped;
- ``meta.executionTrace.winnerProvider`` / ``winnerModel``: which
  provider/model actually answered (openclaw routes across fallbacks).

Everything except ``payloads`` lives under ``meta`` (live-captured); each
accessor also tolerates the same key at the TOP level so a future flattening
does not silently lose data. Every accessor is tolerant of missing/mis-typed
fields — a malformed blob degrades to an empty turn, never raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpenclawTurn:
    """The distilled result of one openclaw turn."""

    text: str
    stop_reason: str
    #: ``provider/model`` that actually answered, or ``None`` when the trace is
    #: absent (used to stamp the assistant message).
    model_id: str | None


def _meta(blob: dict[str, Any]) -> dict[str, Any]:
    meta = blob.get("meta")
    return meta if isinstance(meta, dict) else {}


def _field(blob: dict[str, Any], key: str) -> Any:
    """``meta.<key>`` (the live-captured location), else the top-level key."""
    value = _meta(blob).get(key)
    return value if value is not None else blob.get(key)


def _payload_text(blob: dict[str, Any]) -> str:
    payloads = blob.get("payloads")
    if not isinstance(payloads, list):
        return ""
    parts: list[str] = []
    for item in payloads:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "\n\n".join(parts)


def _stop_reason(blob: dict[str, Any]) -> str:
    completion = _field(blob, "completion")
    if isinstance(completion, dict):
        reason = completion.get("finishReason")
        if isinstance(reason, str) and reason:
            return reason
    reason = _field(blob, "stopReason")
    if isinstance(reason, str) and reason:
        return reason
    return "end_turn"


def _model_id(blob: dict[str, Any]) -> str | None:
    trace = _field(blob, "executionTrace")
    if not isinstance(trace, dict):
        return None
    provider = trace.get("winnerProvider")
    model = trace.get("winnerModel")
    if isinstance(model, str) and model:
        if isinstance(provider, str) and provider:
            return f"{provider}/{model}"
        return model
    return None


def map_openclaw_result(blob: dict[str, Any]) -> OpenclawTurn:
    """Distill one parsed result blob into the turn's text/stop/model.

    The reply text prefers the ``payloads`` chunks (joined with blank lines);
    ``meta.finalAssistantVisibleText`` is the fallback when payloads are absent
    or empty. Tolerant throughout — missing fields yield an empty text and the
    ``end_turn`` default, never an exception.
    """
    text = _payload_text(blob)
    if not text:
        final = _field(blob, "finalAssistantVisibleText")
        if isinstance(final, str):
            text = final
    return OpenclawTurn(text=text, stop_reason=_stop_reason(blob), model_id=_model_id(blob))


__all__ = ["OpenclawTurn", "map_openclaw_result"]
