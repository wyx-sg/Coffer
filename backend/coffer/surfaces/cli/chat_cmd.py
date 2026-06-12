"""`coffer chat` — interactive and one-shot agent chat CLI commands."""

from __future__ import annotations

import sys

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(
    help="Chat with the built-in Coffer agent",
    invoke_without_command=True,
)

# SSE event names produced by the server
_TURN_START = "turn_start"
_TEXT_DELTA = "text_delta"
_TOOL_CALL = "tool_call"
_TOOL_RESULT = "tool_result"
_TURN_DONE = "turn_done"
_TURN_ERROR = "turn_error"


def _create_conversation(c: httpx.Client, model_id: str | None = None) -> str:
    """POST /chat/conversations and return the new conversation id.

    A ``--model`` choice is passed to the built-in agent through ``agent_config``.
    """
    body: dict[str, object] = {}
    if model_id is not None:
        body["agent_config"] = {"model_id": model_id}
    r = c.post("/chat/conversations", json=body)
    r.raise_for_status()
    return str(r.json()["id"])


def _parse_sse_lines(raw: str) -> list[tuple[str, str]]:
    """Parse a raw SSE frame into [(event, data), …] pairs."""
    events: list[tuple[str, str]] = []
    current_event = ""
    current_data = ""
    for line in raw.splitlines():
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            chunk_data = line[len("data:") :].strip()
            current_data = current_data + "\n" + chunk_data if current_data else chunk_data
        elif line == "" and current_event:
            events.append((current_event, current_data))
            current_event = ""
            current_data = ""
    if current_event:
        events.append((current_event, current_data))
    return events


def _stream_sse(c: httpx.Client, conversation_id: str, text: str) -> int:
    """POST a user message and stream SSE events to stdout.

    Returns 0 on turn_done, 1 on turn_error or truncated stream.
    """
    import json as _json

    url = f"/chat/conversations/{conversation_id}/messages"
    body = {"text": text}
    # Long agent turns can exceed any short read deadline; disable the read
    # timeout so the stream stays open for the full turn duration.
    stream_timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)

    try:
        with c.stream("POST", url, json=body, timeout=stream_timeout) as resp:
            if resp.status_code == 409:
                resp.read()
                err = resp.json().get("error", {})
                code = err.get("code", "UNKNOWN")
                msg = err.get("message", resp.text)
                if code == "NO_MODEL_CONFIGURED":
                    typer.echo(
                        "error: no model configured — run `coffer model add` first",
                        err=True,
                    )
                else:
                    typer.echo(f"error: {code}: {msg}", err=True)
                return 1
            if resp.status_code == 404:
                resp.read()
                typer.echo("error: conversation not found", err=True)
                return 1
            if resp.status_code != 200:
                resp.read()
                typer.echo(f"error: HTTP {resp.status_code}: {resp.text}", err=True)
                return 1

            buf = ""
            turn_completed = False
            for chunk in resp.iter_text():
                # Normalise CRLF → LF so SSE frame splitting works on all transports.
                buf += chunk.replace("\r\n", "\n")
                # Process complete SSE frames (terminated by blank line)
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    for evt, data in _parse_sse_lines(frame):
                        if evt == _TEXT_DELTA:
                            try:
                                payload = _json.loads(data)
                                sys.stdout.write(payload.get("text", ""))
                                sys.stdout.flush()
                            except _json.JSONDecodeError:
                                pass
                        elif evt == _TOOL_CALL:
                            try:
                                payload = _json.loads(data)
                                tool_name = payload.get("tool_name", "?")
                                tool_input = payload.get("tool_input", {})
                                typer.echo(f"\n[tool_call] {tool_name}({_json.dumps(tool_input)})")
                            except _json.JSONDecodeError:
                                typer.echo(f"\n[tool_call] {data}")
                        elif evt == _TOOL_RESULT:
                            try:
                                payload = _json.loads(data)
                                tool_name = payload.get("tool_name", "?")
                                output = payload.get("output", "")
                                typer.echo(f"[tool_result] {tool_name}: {output}")
                            except _json.JSONDecodeError:
                                typer.echo(f"[tool_result] {data}")
                        elif evt == _TURN_DONE:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            turn_completed = True
                            return 0
                        elif evt == _TURN_ERROR:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            try:
                                payload = _json.loads(data)
                                code = payload.get("code", "UNKNOWN")
                                msg = payload.get("message", data)
                                typer.echo(f"error: {code}: {msg}", err=True)
                            except _json.JSONDecodeError:
                                typer.echo(f"error: {data}", err=True)
                            turn_completed = True
                            return 1
            if not turn_completed:
                typer.echo("error: stream ended before the turn completed", err=True)
                return 1
            return 0
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        typer.echo(f"error: connection error — {exc}", err=True)
        return 1


@app.callback()
def chat(
    ctx: typer.Context,
    message: str | None = typer.Option(
        None,
        "-m",
        "--message",
        help="One-shot message text",
    ),
    conversation: str | None = typer.Option(
        None,
        "--conversation",
        "-c",
        help="Existing conversation ID to resume",
    ),
    model_id: str | None = typer.Option(
        None,
        "--model",
        help="Model ID to use for a new conversation",
    ),
) -> None:
    """Chat with the Coffer agent.

    One-shot:   coffer chat -m "Hello"
    Interactive: coffer chat
    """
    c, _info = _cli_client.client_or_exit()

    with c:
        # Resolve or create conversation
        conv_id = conversation
        if conv_id is None:
            conv_id = _create_conversation(c, model_id)

        if message is not None:
            # One-shot mode
            exit_code = _stream_sse(c, conv_id, message)
            if exit_code != 0:
                raise typer.Exit(exit_code)
        else:
            # Interactive REPL
            typer.echo(f"[conversation {conv_id}] (type 'exit' or Ctrl-D to quit)")
            while True:
                try:
                    line = typer.prompt("you", prompt_suffix="> ")
                except (typer.Abort, EOFError):
                    typer.echo("")
                    break
                line = line.strip()
                if not line:
                    continue
                if line.lower() in ("exit", "quit"):
                    break
                exit_code = _stream_sse(c, conv_id, line)
                if exit_code != 0:
                    raise typer.Exit(exit_code)
