"""A stand-in model server speaking the OpenAI Responses API's streamed events.

The first request that offers tools is answered with one ``bash`` call
(``echo hi``); every other request with the text ``Hello from the stand-in.``.
Enough for an agent CLI to run a whole turn: a tool, its result, an answer.
"""

from __future__ import annotations

import http.server
import json
import threading
from typing import Any

TEXT = "Hello from the stand-in."


def _sse(out: Any, event: str, data: dict[str, Any]) -> None:
    out.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen: list[dict[str, Any]]

    def do_GET(self) -> None:
        body = json.dumps({"data": [{"id": "stand-in", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("content-length") or 0))
        req = json.loads(raw or b"{}")
        self.seen.append({"path": self.path, "auth": self.headers.get("authorization"), "req": req})
        answered = "function_call_output" in raw.decode(errors="ignore")
        tool = bool(req.get("tools")) and not answered
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("connection", "close")
        self.end_headers()
        out = self.wfile
        base = {
            "id": "resp",
            "object": "response",
            "created_at": 0,
            "model": req.get("model"),
            "status": "in_progress",
            "output": [],
        }
        _sse(
            out,
            "response.created",
            {"type": "response.created", "sequence_number": 0, "response": base},
        )
        if tool:
            args = json.dumps({"command": "echo hi", "description": "say hi"})
            item = {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "bash",
                "arguments": args,
                "status": "completed",
            }
            _sse(
                out,
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "sequence_number": 1,
                    "output_index": 0,
                    "item": dict(item, arguments=""),
                },
            )
            _sse(
                out,
                "response.function_call_arguments.done",
                {
                    "type": "response.function_call_arguments.done",
                    "sequence_number": 2,
                    "item_id": "fc_1",
                    "output_index": 0,
                    "arguments": args,
                },
            )
            _sse(
                out,
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "sequence_number": 3,
                    "output_index": 0,
                    "item": item,
                },
            )
        else:
            part = {"type": "output_text", "text": TEXT, "annotations": []}
            item = {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [part],
            }
            _sse(
                out,
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "sequence_number": 1,
                    "output_index": 0,
                    "item": dict(item, status="in_progress", content=[]),
                },
            )
            _sse(
                out,
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "sequence_number": 2,
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "part": dict(part, text=""),
                },
            )
            _sse(
                out,
                "response.output_text.delta",
                {
                    "type": "response.output_text.delta",
                    "sequence_number": 3,
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": TEXT,
                    "logprobs": [],
                },
            )
            _sse(
                out,
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "sequence_number": 4,
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "text": TEXT,
                    "logprobs": [],
                },
            )
            _sse(
                out,
                "response.content_part.done",
                {
                    "type": "response.content_part.done",
                    "sequence_number": 5,
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "part": part,
                },
            )
            _sse(
                out,
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "sequence_number": 6,
                    "output_index": 0,
                    "item": item,
                },
            )
        usage = {
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
        _sse(
            out,
            "response.completed",
            {
                "type": "response.completed",
                "sequence_number": 9,
                "response": dict(base, status="completed", output=[item], usage=usage),
            },
        )
        out.flush()

    def log_message(self, *args: object) -> None:
        pass


class StandIn:
    """``with StandIn() as s:`` serves on ``s.base_url`` (``…/openai/v1``)."""

    def __enter__(self) -> StandIn:
        self.seen: list[dict[str, Any]] = []
        handler = type("Handler", (_Handler,), {"seen": self.seen})
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/openai/v1"
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
