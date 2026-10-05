"""Turn a custom tool and an agent's arguments into one HTTP request.

Design add-http-custom-tools §3, spec mcp-gateway "Make a custom tool's request
in the gateway". A template's ``{argument}`` holes are filled so that a value
can never change the request's shape:

* a path hole is percent-encoded with no safe characters — ``a/b`` becomes
  ``a%2Fb`` — so a value adds no segment, query or host;
* a query pair whose value is one hole is dropped when the argument is absent
  and repeated for a list; every key and value is re-encoded;
* a body hole outside a JSON string becomes the value's JSON encoding
  (``null`` when absent), inside a string its JSON-escaped text, and the result
  must parse as JSON;
* an environment's variable (``{env:NAME}``, design
  align-cli-with-ui-and-add-tool-environments D4) is filled first, encoded the
  same way for where it sits; its value holds no braces, so it can never open
  an argument hole.

Before any of it the arguments are validated against the tool's JSON Schema
(spec mcp-gateway "Validate a custom tool's arguments before any request"):
every way they break it is returned as one :class:`ArgumentsInvalid`, so no
request is made from arguments the schema refuses.

Pure: the standard library only. The auth header is not added here — the
adapter adds it last, from the secret it was handed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from coffer.domain.error_base import CofferError
from coffer.domain.mcp.json_schema import SchemaError, validate

#: ``{name}`` — the name as an OpenAPI parameter or a JSON Schema property may spell it.
_HOLE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.\-]*)\}")
#: ``{env:NAME}`` — an environment's variable.
_ENV = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]{0,63})\}")
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class RenderError(ValueError):
    """The arguments cannot make a request: a required one is missing, or the
    body did not come out as JSON. Returned to the agent as a tool error."""


class ArgumentsInvalid(RenderError, CofferError):  # noqa: N818
    """The arguments break the tool's schema; ``errors`` names every failure."""

    code = "CUSTOM_TOOL_ARGUMENTS_INVALID"

    def __init__(self, errors: list[SchemaError]) -> None:
        self.errors = errors
        lines = "; ".join(f"{e.path or '/'}: {e.message}" for e in errors)
        super().__init__(f"the arguments do not match the tool's schema — {lines}")
        self.error_details: dict[str, object] = {"errors": [e.as_dict() for e in errors]}

    def details(self) -> list[dict[str, str]]:
        return [e.as_dict() for e in self.errors]


def _sub_env(text: str, variables: Mapping[str, str], encode: Callable[[str], str]) -> str:
    def one(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in variables:
            raise RenderError(f"the environment defines no variable {name!r}")
        return encode(variables[name])

    return _ENV.sub(one, text)


def _raw(text: str) -> str:
    return text


def holes_in(text: str) -> set[str]:
    return set(_HOLE.findall(text))


def template_holes(path: str, headers: Mapping[str, str], body_template: str | None) -> set[str]:
    """Every argument a tool's request template names."""
    names = holes_in(path)
    for value in headers.values():
        names |= holes_in(value)
    if body_template:
        names |= holes_in(body_template)
    return names


@dataclass(frozen=True)
class RenderedRequest:
    method: str
    #: Without the base URL's host part changed: base URL + rendered path.
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _fill_text(template: str, args: Mapping[str, Any], *, encode: bool) -> str | None:
    """Fill every hole; ``None`` when a hole's argument is absent."""
    out: list[str] = []
    pos = 0
    for m in _HOLE.finditer(template):
        name = m.group(1)
        if name not in args or args[name] is None:
            return None
        text = _scalar(args[name])
        out.append(template[pos : m.start()])
        out.append(quote(text, safe="") if encode else text)
        pos = m.end()
    out.append(template[pos:])
    return "".join(out)


def _render_path(path_part: str, args: Mapping[str, Any]) -> str:
    filled = _fill_text(path_part, args, encode=True)
    if filled is None:
        missing = sorted(n for n in holes_in(path_part) if args.get(n) is None)
        raise RenderError("missing path argument(s): " + ", ".join(missing))
    return filled


def _render_query(
    query_part: str, args: Mapping[str, Any], env_vars: Mapping[str, str]
) -> list[str]:
    pairs: list[str] = []
    for raw in query_part.split("&"):
        if not raw:
            continue
        key, _, value = raw.partition("=")
        key, value = _sub_env(key, env_vars, _raw), _sub_env(value, env_vars, _raw)
        whole = _HOLE.fullmatch(value)
        if whole is not None:
            arg = args.get(whole.group(1))
            if arg is None:
                continue
            values = arg if isinstance(arg, list) else [arg]
            pairs.extend(f"{quote(key, safe='')}={quote(_scalar(v), safe='')}" for v in values)
            continue
        filled = _fill_text(value, args, encode=False)
        if filled is None:
            continue
        pairs.append(f"{quote(key, safe='')}={quote(filled, safe='')}")
    return pairs


def _render_body_template(
    template: str, args: Mapping[str, Any], variables: Mapping[str, str]
) -> bytes:
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(template):
        ch = template[i]
        if in_string and ch == "\\":
            out.append(template[i : i + 2])
            i += 2
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            i += 1
            continue
        if ch == "{":
            env = _ENV.match(template, i)
            if env is not None:
                text = _sub_env(env.group(0), variables, _raw)
                out.append(json.dumps(text)[1:-1] if in_string else text)
                i = env.end()
                continue
            m = _HOLE.match(template, i)
            if m is not None:
                value = args.get(m.group(1))
                if in_string:
                    out.append("" if value is None else json.dumps(_scalar(value))[1:-1])
                else:
                    out.append(json.dumps(value))
                i = m.end()
                continue
        out.append(ch)
        i += 1
    text = "".join(out)
    try:
        json.loads(text)
    except ValueError as e:
        raise RenderError(f"the body template did not produce valid JSON: {e}") from e
    return text.encode("utf-8")


def render_request(
    *,
    base_url: str,
    method: str,
    path: str,
    group_headers: Mapping[str, str],
    tool_headers: Mapping[str, str],
    body_template: str | None,
    input_schema: Mapping[str, Any],
    arguments: Mapping[str, Any] | None,
    variables: Mapping[str, str] | None = None,
) -> RenderedRequest:
    args: dict[str, Any] = dict(arguments or {})
    errors = validate(dict(input_schema), args)
    if errors:
        raise ArgumentsInvalid(errors)
    env_vars: Mapping[str, str] = variables or {}

    path_part, _, query_part = path.partition("?")
    path_part = _sub_env(path_part, env_vars, lambda v: quote(v, safe="/"))
    rendered = _render_path(path_part, args)
    query = _render_query(query_part, args, env_vars)
    url = base_url.rstrip("/") + rendered + ("?" + "&".join(query) if query else "")

    headers = dict(group_headers)
    for name, template in tool_headers.items():
        value = _fill_text(_sub_env(template, env_vars, _raw), args, encode=False)
        if value is not None:
            headers[name] = value

    used = template_holes(path, tool_headers, body_template)
    body: bytes | None = None
    if body_template:
        body = _render_body_template(body_template, args, env_vars)
    elif method in _BODY_METHODS:
        rest = {k: v for k, v in args.items() if k not in used}
        if rest:
            body = json.dumps(rest).encode("utf-8")
    if body is not None:
        headers.setdefault("Content-Type", "application/json")
    return RenderedRequest(method=method, url=url, headers=headers, body=body)


__all__ = [
    "ArgumentsInvalid",
    "RenderError",
    "RenderedRequest",
    "holes_in",
    "render_request",
    "template_holes",
]
