"""The command line contract every management command shares.

Spec resource-framework "Offer every management operation on the command
line"; design align-cli-with-ui-and-add-tool-environments D3.

* ``--json``: the daemon's answer verbatim on stdout; a failure as
  ``{"error": {"code", "message", "details"}, "exit_code"}`` on stderr.
* A body from ``--data '<json>'``, ``--data @file`` or ``--data -`` (stdin),
  with repeatable ``--set a.b=value`` merged over it (the value parsed as JSON
  when it parses, else taken as text).
* Exit codes: :class:`ExitCode`; the daemon's ``error.code`` is passed through.
* Nothing prompts: a command reads stdin only when told to with ``-``.

A change the daemon saved but that waits for a person's approval is reported
with the approval ids and the command that approves them, exit 9.
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NoReturn

import httpx
import typer

from coffer.surfaces.cli import _client
from coffer.surfaces.cli._options import ExitCode

JSON_HELP = "Print the daemon's answer as JSON on stdout (errors as JSON on stderr)."
DATA_HELP = "Request body: JSON text, @path to read a file, or - to read stdin."
SET_HELP = "Set one body field: key=value (dotted keys nest; the value is JSON when it parses)."


def json_option() -> Any:
    return typer.Option(False, "--json", help=JSON_HELP)


def data_option(help_text: str = DATA_HELP) -> Any:
    return typer.Option(None, "--data", "-d", help=help_text)


def set_option() -> Any:
    return typer.Option(None, "--set", help=SET_HELP)


def fail(
    code: str,
    message: str,
    exit_code: ExitCode,
    *,
    as_json: bool,
    details: Mapping[str, Any] | None = None,
) -> NoReturn:
    render_failure(code, message, int(exit_code), as_json=as_json, details=details)
    raise typer.Exit(int(exit_code))


def render_failure(
    code: str,
    message: str,
    exit_code: int,
    *,
    as_json: bool,
    details: Mapping[str, Any] | None = None,
) -> None:
    if as_json:
        envelope = {
            "error": {"code": code, "message": message, "details": dict(details or {})},
            "exit_code": exit_code,
        }
        typer.echo(json.dumps(envelope, ensure_ascii=False), err=True)
        return
    typer.echo(message, err=True)
    handoff = (details or {}).get("handoff")
    if isinstance(handoff, dict) and handoff.get("prompt"):
        typer.echo("\nTo hand this to your agent, give it this prompt:\n", err=True)
        typer.echo(str(handoff["prompt"]), err=True)
    ids = (details or {}).get("approval_ids")
    if ids and code == "SECRET_BINDING_PENDING":
        typer.echo(f"next: coffer approval approve {' '.join(ids)}", err=True)


def exit_code_for(status: int, code: str | None) -> ExitCode:
    """The exit code of a daemon error (the table in ``_options``)."""
    if code in ("SECRET_BINDING_PENDING",):
        return ExitCode.APPROVAL_PENDING
    if code in ("SECRET_MISSING", "SECRET_LOCKED", "SECRET_BINDING_REJECTED", "SECRET_UNREADABLE"):
        return ExitCode.SECRET_ISSUE
    if code == "PRESENCE_GRANT_INVALID":
        return ExitCode.PRESENCE_NOT_CONFIRMED
    if status in (502, 504) and code not in (None, "UPSTREAM_UNAVAILABLE"):
        return ExitCode.UPSTREAM_TEST_FAILED
    return {
        404: ExitCode.NOT_FOUND,
        409: ExitCode.CONFLICT,
        400: ExitCode.INVALID_INPUT,
        422: ExitCode.INVALID_INPUT,
    }.get(status, ExitCode.GENERIC)


def _envelope(r: httpx.Response) -> tuple[str, str, dict[str, Any]]:
    data: Any = None
    with contextlib.suppress(Exception):
        data = r.json()
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return (
            str(error.get("code") or f"HTTP_{r.status_code}"),
            str(error.get("message") or r.reason_phrase),
            dict(error.get("details") or {}),
        )
    detail = data.get("detail") if isinstance(data, dict) else None
    return f"HTTP_{r.status_code}", str(detail or r.reason_phrase or r.text[:200]), {}


def check(r: httpx.Response, *, as_json: bool) -> Any:
    """The response's JSON body (``None`` for no content), or render its error and exit."""
    if r.is_success:
        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text
    code, message, details = _envelope(r)
    if code == "FEATURE_DISABLED":
        key = details.get("feature", "?")
        message = f"{key} is switched off on this machine — run: coffer config set feature.{key} on"
    fail(code, message, exit_code_for(r.status_code, code), as_json=as_json, details=details)


def call(
    method: str,
    path: str,
    *,
    as_json: bool,
    params: Mapping[str, Any] | None = None,
    body: Any = None,
    timeout: float | None = None,
    files: Mapping[str, tuple[str, bytes]] | None = None,
    form: Mapping[str, str] | None = None,
) -> Any:
    """One request to the daemon (started on demand), its JSON answer or an exit.

    ``files`` and ``form`` send a multipart upload, as the page's file picker does."""
    client, _info = _client.client_or_exit()
    with client as c:
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = {k: v for k, v in params.items() if v is not None}
        if body is not None:
            kwargs["json"] = body
        if timeout is not None:
            kwargs["timeout"] = timeout
        if files is not None:
            kwargs["files"] = dict(files)
            kwargs["data"] = dict(form or {})
        try:
            r = c.request(method, path, **kwargs)
        except httpx.TransportError:
            fail(
                "DAEMON_UNREACHABLE",
                "daemon not reachable — it may have crashed; check ~/.coffer/logs/daemon.log",
                ExitCode.DAEMON_UNREACHABLE,
                as_json=as_json,
            )
        return check(r, as_json=as_json)


# --- input --------------------------------------------------------------------


def read_text(value: str, *, as_json: bool) -> str:
    """``-`` reads stdin, ``@path`` reads a file, anything else is the text itself."""
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            fail(
                "CLI_INVALID_INPUT",
                f"cannot read {path}: {e}",
                ExitCode.INVALID_INPUT,
                as_json=as_json,
            )
    return value


def parse_json(text: str, what: str, *, as_json: bool) -> Any:
    try:
        return json.loads(text)
    except ValueError as e:
        fail(
            "CLI_INVALID_INPUT",
            f"{what} is not valid JSON: {e}",
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )


def _value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def apply_sets(body: dict[str, Any], sets: list[str] | None, *, as_json: bool) -> dict[str, Any]:
    for item in sets or []:
        key, eq, raw = item.partition("=")
        if not eq or not key:
            fail(
                "CLI_INVALID_INPUT",
                f"--set takes key=value, got {item!r}",
                ExitCode.INVALID_INPUT,
                as_json=as_json,
            )
        node = body
        parts = key.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = _value(raw)
    return body


def body_from(
    data: str | None,
    sets: list[str] | None,
    *,
    as_json: bool,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """``base``, then ``--data``, then each ``--set``, merged in that order."""
    body: dict[str, Any] = dict(base or {})
    if data is not None:
        loaded = parse_json(read_text(data, as_json=as_json), "--data", as_json=as_json)
        if not isinstance(loaded, dict):
            fail(
                "CLI_INVALID_INPUT",
                "--data must be a JSON object",
                ExitCode.INVALID_INPUT,
                as_json=as_json,
            )
        body.update(loaded)
    return apply_sets(body, sets, as_json=as_json)


# --- output -------------------------------------------------------------------


def emit(value: Any, *, as_json: bool, human: Callable[[Any], None] | None = None) -> None:
    if as_json:
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        return
    if human is not None:
        human(value)
        return
    if value is None:
        typer.echo("done")
    elif isinstance(value, (dict, list)):
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(str(value))


def table(rows: list[Mapping[str, Any]], columns: list[str]) -> None:
    """A plain aligned table of ``columns`` (no colours: agents read it)."""
    if not rows:
        typer.echo("(none)")
        return
    cells = [[_cell(r.get(c)) for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]
    typer.echo("  ".join(c.upper().ljust(widths[i]) for i, c in enumerate(columns)).rstrip())
    for row in cells:
        typer.echo("  ".join(v.ljust(widths[i]) for i, v in enumerate(row)).rstrip())


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= 60 else text[:57] + "..."


def pending_approvals(value: Any) -> list[str]:
    """The approval ids an answer says a change waits on, wherever it puts them."""
    if not isinstance(value, dict):
        return []
    ids: list[str] = []
    for key in ("pending_approvals", "approval_ids"):
        found = value.get(key)
        if isinstance(found, list):
            ids += [str(i) for i in found]
    return list(dict.fromkeys(ids))


def report_pending(value: Any, *, as_json: bool) -> None:
    """Exit 9 with the approve command when ``value`` waits on approvals."""
    ids = pending_approvals(value)
    if not ids:
        return
    command = "coffer approval approve " + " ".join(ids)
    if as_json:
        typer.echo(
            json.dumps(
                {"status": "pending_approval", "approval_ids": ids, "next": command},
                ensure_ascii=False,
            ),
            err=True,
        )
    else:
        typer.echo(f"waiting for approval: {', '.join(ids)}", err=True)
        typer.echo(f"next: {command}", err=True)
    raise typer.Exit(int(ExitCode.APPROVAL_PENDING))


__all__ = [
    "apply_sets",
    "body_from",
    "call",
    "check",
    "data_option",
    "emit",
    "exit_code_for",
    "fail",
    "json_option",
    "parse_json",
    "pending_approvals",
    "read_text",
    "render_failure",
    "report_pending",
    "set_option",
    "table",
]
