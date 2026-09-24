"""Generate docs-site/reference/rest-api.md from the daemon's OpenAPI document.

The route table comes from ``create_app().openapi()`` — the same document the
daemon serves at ``/api/v1/openapi.json`` — so every route on the page is one
the daemon mounts. Building the app runs no lifespan: nothing binds a port,
opens the database or touches ``~/.coffer``. Output is deterministic, which is
what lets ``scripts/check_cli_reference.py`` fail CI when the page drifts.

    .venv/bin/python docs-site/scripts/gen_rest_reference.py          # write the page
    .venv/bin/python docs-site/scripts/gen_rest_reference.py --stdout # print it
"""

# ruff: noqa: E501 — HEADER is page prose, wrapped as Markdown, not code.
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
OUTPUT = REPO_ROOT / "docs-site" / "reference" / "rest-api.md"

sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(HERE))

from gen_cli_reference import _escape_prose, _paragraphs  # noqa: E402

_METHOD_ORDER = ("get", "post", "put", "patch", "delete", "head", "options")

HEADER = """\
---
title: REST API reference
description: The daemon's management API — base URL, authentication, errors, tracing and every route.
---

# REST API reference

The Coffer daemon serves a JSON management API on loopback. The web UI, the desktop app and
the `coffer` CLI all use it; you can call it too, for scripting. This page covers the
conventions every route shares and lists every route the daemon mounts.

::: info Generated page
The route tables below are generated from the daemon's OpenAPI document by
`docs-site/scripts/gen_rest_reference.py`. Regenerate with `make docs-reference`;
`make lint` fails when the page and the daemon disagree.
:::

## Base URL

```text
http://127.0.0.1:8000/api/v1
```

The daemon binds `127.0.0.1` only. The port is `8000` unless you set another one with
`coffer daemon port set <port>`; the port of the running daemon is always in
`~/.coffer/daemon.json`. See [Running the daemon](/guides/daemon).

The daemon also serves its live OpenAPI document at `/api/v1/openapi.json`, and the MCP
endpoint for agents at `/mcp` (see [MCP tools](/reference/mcp-tools)).

## Authentication

Every route except `GET /api/v1/daemon/status` requires the daemon's API token in the
`X-Coffer-Token` header. The daemon generates a fresh token each time it starts and writes it,
with the port and its process id, to `~/.coffer/daemon.json` (mode `0600`):

```sh
TOKEN=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.coffer/daemon.json")))["token"])')
curl -s -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:8000/api/v1/resources
```

| Header | Direction | Meaning |
| --- | --- | --- |
| `X-Coffer-Token` | request | The API token. Missing or wrong: `401 UNAUTHENTICATED`. Before the daemon is ready: `503 DAEMON_NOT_READY`. |
| `X-Coffer-Actor` | request | Optional. Who is acting, recorded in the audit log: a lowercase identifier matching `[a-z][a-z0-9_-]{0,31}` (the CLI sends `cli`, the web UI `ui`). Defaults to `api`; any other shape is `400`. |
| `X-Coffer-Trace` | both | Optional on requests; always on responses. See [Tracing](#tracing). |

`coffer daemon rotate-token` replaces the token and rewrites `daemon.json`.

::: warning Loopback only
The daemon refuses any request whose `Host` header does not name a loopback address
(`127.0.0.1`, `localhost`, `::1`) with `421 HOST_NOT_LOOPBACK`. This defends against DNS
rebinding; see the [security model](/architecture/security).
:::

## Errors

Every error response has the same envelope:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "no mcp_server named 'ghost'",
    "details": {}
  }
}
```

`code` is stable and machine-readable; `message` is for people; `details` carries structured
context such as `reason`, `hint` or `feature` when the error has one. Request-validation
failures are `422 CONFIG_INVALID` and deliberately do not echo the submitted values. The full
list of codes and their HTTP statuses is in [Error codes](/reference/error-codes).

## Tracing

The daemon gives every request a trace id and returns it in the `X-Coffer-Trace` response
header, error or not. Every daemon log line written while serving that request carries the
same id as `trace_id`, so you can find a failed request's log records with
`grep <trace-id> ~/.coffer/logs/daemon.log`. You may send your own `X-Coffer-Trace` to tie
several calls together; the daemon keeps only `A-Z a-z 0-9 . _ : -` and at most 64
characters, and generates a fresh id if nothing survives. See
[Observability](/architecture/observability).

## Experimental features

Routes that belong to an [experimental feature](/guides/experimental-features) answer
`404 FEATURE_DISABLED` (with `details.feature`) while that feature is switched off on the
machine, exactly like a route the build does not have. The tables below mark those groups.

## Routes
"""


def _first_sentence(text: str) -> str:
    paras = _paragraphs(text)
    if not paras:
        return ""
    head = re.split(r"(?<=[.!?])\s", paras[0].replace("\n", " "), maxsplit=1)[0]
    return head


def _summary(op: dict[str, Any]) -> str:
    text = _first_sentence(op.get("description") or "") or _escape_prose(op.get("summary") or "")
    # Docstrings cite their decision records inline; the page links those elsewhere.
    text = re.sub(r"\s*\([^()]*\bADR\b[^()]*\)", "", text)
    text = re.sub(r",?\s*ADR [a-z0-9-]+", "", text)
    return text.replace("|", "\\|")


def _group_of(path: str, op: dict[str, Any]) -> str:
    tags = op.get("tags") or []
    if tags:
        return str(tags[0])
    parts = [p for p in path.split("/") if p]
    return parts[2] if len(parts) > 2 and parts[:2] == ["api", "v1"] else parts[0]


def _load_openapi() -> dict[str, Any]:
    from coffer.surfaces.http.app import create_app

    logging.disable(logging.CRITICAL)
    try:
        return create_app().openapi()
    finally:
        logging.disable(logging.NOTSET)


def render() -> str:
    from coffer.domain.features import feature_for_path

    doc = _load_openapi()
    groups: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, ops in doc["paths"].items():
        for method in _METHOD_ORDER:
            op = ops.get(method)
            if op is None:
                continue
            groups.setdefault(_group_of(path, op), []).append((method, path, op))

    total = sum(len(v) for v in groups.values())
    lines = [HEADER]
    lines.append(
        f"The daemon mounts {total} operations in {len(groups)} groups. Groups follow the "
        "order the daemon registers its routers in; paths are relative to the host root."
    )
    lines.append("")
    lines += ["| Group | Operations |", "| --- | --- |"]
    for name, ops in groups.items():
        lines.append(f"| [{name}](#{name}) | {len(ops)} |")
    lines.append("")
    for name, ops in groups.items():
        lines += [f"### {name}", ""]
        features = sorted({f for f in (feature_for_path(p) for _, p, _ in ops) if f})
        for feature in features:
            lines += [
                f"::: tip Experimental feature `{feature}`",
                f"Routes under this feature's prefix answer `404 FEATURE_DISABLED` while `{feature}` is off.",
                ":::",
                "",
            ]
        lines += ["| Method | Path | Summary |", "| --- | --- | --- |"]
        for method, path, op in ops:
            headers = {
                p["name"].lower() for p in op.get("parameters", []) if p.get("in") == "header"
            }
            note = "" if "x-coffer-token" in headers else " (no token required)"
            lines.append(f"| `{method.upper()}` | `{path}` | {_summary(op)}{note} |")
        lines.append("")
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--stdout" in argv:
        sys.stdout.write(text)
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
