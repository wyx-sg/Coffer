"""Unit tests for the openclaw result-blob mapping (non-streaming, ADR-044).

The fixture mirrors the REAL ``openclaw agent --json --local`` blob (captured
live on openclaw 2026.6.11): ``payloads`` is top-level; the flattened
``finalAssistantVisibleText``, ``stopReason`` / ``completion.finishReason``,
and the routing ``executionTrace`` all live under ``meta``.
"""

from __future__ import annotations

from typing import Any

from coffer.infrastructure.chat.openclaw_mapping import map_openclaw_result


def _blob(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "payloads": [{"text": "PONG", "mediaUrl": None}],
        "meta": {
            "finalAssistantVisibleText": "PONG",
            "stopReason": "stop",
            "completion": {"stopReason": "stop", "finishReason": "stop"},
            "executionTrace": {
                "winnerProvider": "deepseek",
                "winnerModel": "deepseek-v4-flash",
                "fallbackUsed": False,
                "runner": "embedded",
            },
        },
    }
    base.update(overrides)
    return base


def _meta(**overrides: Any) -> dict[str, Any]:
    blob = _blob()
    blob["meta"] = {**blob["meta"], **overrides}
    return blob


def test_maps_payload_text_stop_reason_and_winner_model() -> None:
    turn = map_openclaw_result(_blob())
    assert turn.text == "PONG"
    # meta.completion.finishReason wins over meta.stopReason.
    assert turn.stop_reason == "stop"
    assert turn.model_id == "deepseek/deepseek-v4-flash"


def test_joins_multiple_payload_chunks_with_blank_lines() -> None:
    turn = map_openclaw_result(_blob(payloads=[{"text": "a"}, {"text": ""}, {"text": "b"}]))
    assert turn.text == "a\n\nb"


def test_falls_back_to_meta_final_visible_text_when_payloads_absent() -> None:
    turn = map_openclaw_result(_meta(finalAssistantVisibleText="fallback") | {"payloads": None})
    assert turn.text == "fallback"
    blob = _meta(finalAssistantVisibleText="fallback")
    blob["payloads"] = []
    assert map_openclaw_result(blob).text == "fallback"


def test_stop_reason_falls_back_to_meta_stop_reason_then_default() -> None:
    assert map_openclaw_result(_meta(completion={}, stopReason="length")).stop_reason == "length"
    assert map_openclaw_result(_meta(completion=None, stopReason=None)).stop_reason == "end_turn"
    assert map_openclaw_result({}).stop_reason == "end_turn"


def test_top_level_keys_are_tolerated_as_a_fallback_location() -> None:
    # A future flattening of the blob must not silently lose data: the same
    # keys are honoured at the top level when meta lacks them.
    blob = {
        "payloads": [],
        "finalAssistantVisibleText": "flat",
        "stopReason": "length",
        "executionTrace": {"winnerModel": "m1"},
    }
    turn = map_openclaw_result(blob)
    assert turn.text == "flat"
    assert turn.stop_reason == "length"
    assert turn.model_id == "m1"


def test_model_id_tolerates_partial_trace() -> None:
    assert map_openclaw_result(_meta(executionTrace=None)).model_id is None
    assert map_openclaw_result(_meta(executionTrace={})).model_id is None
    only_model = map_openclaw_result(_meta(executionTrace={"winnerModel": "m1"}))
    assert only_model.model_id == "m1"


def test_malformed_blob_degrades_to_empty_turn() -> None:
    turn = map_openclaw_result({"payloads": [42, "x", {"text": 7}], "meta": "weird"})
    assert turn.text == ""
    assert turn.stop_reason == "end_turn"
    assert turn.model_id is None
