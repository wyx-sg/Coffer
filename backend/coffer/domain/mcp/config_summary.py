"""An MCP server's config and output as a hand-off prompt may quote them.

A hand-off (``domain/handoff.py``) tells the person's agent how a server is
started and what it printed, so the agent can find why it will not start
(spec mcp-gateway "Hand a failing MCP server's diagnosis to an agent"). The
prompt is copied into another program, so nothing secret may be in it:

* environment variables and HTTP headers are named, never valued — a static
  value can still be a secret a person pasted in, and a secret ref's value
  is only ever resolved at spawn time;
* an argument, a URL's query parameter or a log line that looks like it
  carries a secret (a ``--token`` flag's value, ``api_key=…``, a well-known
  token shape, a URL's ``user:pass@``) reads :data:`SECRET_PLACEHOLDER`.

Pure text rules; no I/O.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: What a value that is or looks like a secret reads as.
SECRET_PLACEHOLDER = "<secret>"

#: A key or flag name that looks like it holds a secret.
_SECRET_NAME = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|PWD|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL|AUTH)",
    re.IGNORECASE,
)
#: Well-known token shapes, wherever they appear.
_TOKEN_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9._-]{20,}"),
    re.compile(r"coffer://secret/\S+"),
)
#: ``name=value`` / ``name: value`` where the name looks secret.
_ASSIGNMENT = re.compile(
    r"(?P<name>[A-Za-z0-9_.-]*"
    + _SECRET_NAME.pattern
    + r"[A-Za-z0-9_.-]*)(?P<sep>\s*[=:]\s*)(?P<value>\"[^\"]*\"|'[^']*'|[^\s&,;]+)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_URL_USERINFO = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/\s@]+@", re.IGNORECASE)


def scrub(text: str) -> str:
    """``text`` with anything that looks like a secret replaced."""
    for pattern in _TOKEN_SHAPES:
        text = pattern.sub(SECRET_PLACEHOLDER, text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} {SECRET_PLACEHOLDER}", text)
    text = _URL_USERINFO.sub(lambda m: f"{m.group('scheme')}{SECRET_PLACEHOLDER}@", text)
    return _ASSIGNMENT.sub(
        lambda m: (
            f"{m.group('name')}{m.group('sep')}{SECRET_PLACEHOLDER}"
            if m.group("value") != SECRET_PLACEHOLDER
            else m.group(0)
        ),
        text,
    )


def _redact_args(args: Iterable[str]) -> list[str]:
    """The arguments, with the value after a secret-named flag and any
    secret-looking argument replaced."""
    out: list[str] = []
    after_secret_flag = False
    for arg in args:
        if after_secret_flag and not arg.startswith("-"):
            out.append(SECRET_PLACEHOLDER)
            after_secret_flag = False
            continue
        after_secret_flag = (
            arg.startswith("-") and "=" not in arg and bool(_SECRET_NAME.search(arg))
        )
        out.append(scrub(arg))
    return out


def redacted_command_line(command: str, args: Iterable[str]) -> str:
    """The launcher and its arguments as one shell-quoted line, redacted."""
    return shlex.join([scrub(command), *_redact_args(args)])


def redacted_url(url: str) -> str:
    """A URL with its ``user:pass@`` and its secret-named query values replaced."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return scrub(url)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = f"{SECRET_PLACEHOLDER}@{netloc.rsplit('@', 1)[1]}"
    query = urlencode(
        [
            (k, SECRET_PLACEHOLDER if _SECRET_NAME.search(k) else scrub(v))
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
        ],
        safe="<>",
    )
    return scrub(urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment)))


def _names(values: object) -> list[str]:
    return sorted(str(k) for k in values) if isinstance(values, Mapping) else []


def command_line_of(config: Mapping[str, Any]) -> str | None:
    """A stdio server's redacted command line; ``None`` for any other config."""
    transport = config.get("transport")
    if not isinstance(transport, Mapping) or transport.get("type") != "stdio":
        return None
    args = transport.get("args")
    return redacted_command_line(
        str(transport.get("command") or ""),
        [str(a) for a in args] if isinstance(args, list) else [],
    )


def config_summary(config: Mapping[str, Any]) -> tuple[str, ...]:
    """How the server is reached, one short line each: transport, command line
    or URL, working directory, and the NAMES of its environment variables,
    headers and stored secrets — never a value."""
    transport = config.get("transport")
    if not isinstance(transport, Mapping):
        return ("Its config has no transport.",)
    kind = str(transport.get("type") or "unknown")
    lines: list[str] = []
    if kind == "stdio":
        lines.append(f"Transport: stdio, started as `{command_line_of(config)}`.")
        if transport.get("cwd"):
            lines.append(f"Working directory: {transport['cwd']}.")
        env = _names(transport.get("env"))
        if env:
            lines.append(f"Environment variables it sets (values not shown): {', '.join(env)}.")
    elif kind == "http":
        lines.append(f"Transport: Streamable HTTP at {redacted_url(str(transport.get('url')))}.")
        headers = _names(transport.get("headers"))
        if headers:
            lines.append(f"Headers it sends (values not shown): {', '.join(headers)}.")
    else:
        lines.append(f"Transport: {kind}.")
    secrets = _names(transport.get("credential_refs"))
    if secrets:
        lines.append(
            "Secrets Coffer stores and passes it at start (values not shown): "
            + ", ".join(secrets)
            + "."
        )
    return tuple(lines)


__all__ = [
    "SECRET_PLACEHOLDER",
    "command_line_of",
    "config_summary",
    "redacted_command_line",
    "redacted_url",
    "scrub",
]
