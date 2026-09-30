"""Read an OpenAPI 3.x document into custom tools, and plan a re-import.

Spec mcp-gateway "Import custom tools from an OpenAPI document"; design
add-http-custom-tools §8. The document arrives already parsed (JSON or YAML is
the adapter's business); this module turns its operations into draft
:class:`~coffer.domain.mcp.http_api.HttpApiTool` s and compares a new reading
with a group's tools.

Pure: the standard library and the domain only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from pydantic import ValidationError

from coffer.domain.mcp.http_api import HTTP_METHODS, HttpApiTool, HttpApiTransport, OpenApiSource

_HOLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
_REF_DEPTH = 24


class OpenApiError(ValueError):
    """The document is not an OpenAPI 3.x document Coffer can read."""


@dataclass(frozen=True)
class DraftOperation:
    key: str  # "<METHOD> <path>"
    tool: HttpApiTool
    summary: str | None = None


@dataclass(frozen=True)
class OpenApiReading:
    title: str | None
    version: str | None
    base_url: str | None
    auth_header: str | None
    auth_prefix: str
    operations: list[DraftOperation]
    warnings: list[str] = field(default_factory=list)

    def by_key(self) -> dict[str, DraftOperation]:
        return {op.key: op for op in self.operations}


def _resolve(
    node: Any, doc: Mapping[str, Any], depth: int = 0, seen: frozenset[str] = frozenset()
) -> Any:
    """Inline local ``#/…`` references; a cycle or a foreign ref becomes ``{}``."""
    if depth > _REF_DEPTH:
        return {}
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/") or ref in seen:
                return {}
            target: Any = doc
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or part not in target:
                    return {}
                target = target[part]
            return _resolve(target, doc, depth + 1, seen | {ref})
        return {k: _resolve(v, doc, depth + 1, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(v, doc, depth + 1, seen) for v in node]
    return node


def _snake(text: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return re.sub(r"_+", "_", text)


def _tool_name(operation_id: Any, method: str, path: str, taken: set[str]) -> str:
    base = _snake(operation_id) if isinstance(operation_id, str) else ""
    if not base:
        words = [w for w in re.split(r"[^A-Za-z0-9]+", path) if w]
        base = _snake("_".join([method.lower(), *words])) or method.lower()
    if not base[0].isalnum():
        base = "op_" + base
    base = base[:40].rstrip("_") or "op"
    name, n = base, 2
    while name in taken:
        suffix = f"_{n}"
        name = base[: 40 - len(suffix)] + suffix
        n += 1
    taken.add(name)
    return name


def _base_url(doc: Mapping[str, Any], source_url: str | None) -> str | None:
    servers = doc.get("servers")
    if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
        return None
    url = servers[0].get("url")
    if not isinstance(url, str) or not url:
        return None
    for var, spec in (servers[0].get("variables") or {}).items():
        default = spec.get("default") if isinstance(spec, dict) else None
        if isinstance(default, str):
            url = url.replace("{" + var + "}", default)
    if "://" not in url:
        if not source_url:
            return None
        url = urljoin(source_url, url)
    return url.rstrip("/") or None


def _auth(doc: Mapping[str, Any]) -> tuple[str | None, str]:
    schemes = (doc.get("components") or {}).get("securitySchemes") or {}
    if not isinstance(schemes, dict):
        return None, ""
    order: list[str] = []
    for requirement in doc.get("security") or []:
        if isinstance(requirement, dict):
            order.extend(str(k) for k in requirement)
    order.extend(str(k) for k in schemes if k not in order)
    for name in order:
        scheme = schemes.get(name)
        if not isinstance(scheme, dict):
            continue
        kind = scheme.get("type")
        if kind == "http":
            which = str(scheme.get("scheme", "")).lower()
            if which == "bearer":
                return "Authorization", "Bearer "
            if which == "basic":
                return "Authorization", "Basic "
        if (
            kind == "apiKey"
            and scheme.get("in") == "header"
            and isinstance(scheme.get("name"), str)
        ):
            return str(scheme["name"]), ""
        if kind in ("oauth2", "openIdConnect"):
            return "Authorization", "Bearer "
    return None, ""


def _json_body_schema(body: Any) -> tuple[dict[str, Any] | None, bool]:
    if not isinstance(body, dict):
        return None, False
    content = body.get("content") or {}
    if not isinstance(content, dict):
        return None, False
    for media, spec in content.items():
        if media == "application/json" or media.endswith("+json"):
            schema = spec.get("schema") if isinstance(spec, dict) else None
            return (schema if isinstance(schema, dict) else {}), bool(body.get("required"))
    return None, bool(body.get("required"))


def _operation(
    method: str,
    path: str,
    path_item: Mapping[str, Any],
    op: Mapping[str, Any],
    taken: set[str],
    warnings: list[str],
) -> DraftOperation | None:
    key = f"{method} {path}"
    params: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in [*(path_item.get("parameters") or []), *(op.get("parameters") or [])]:
        if isinstance(raw, dict) and isinstance(raw.get("name"), str):
            params[(str(raw["name"]), str(raw.get("in", "")))] = raw
    properties: dict[str, Any] = {}
    required: list[str] = []
    query: list[str] = []
    for (name, where), param in params.items():
        if where not in ("path", "query"):
            continue  # header and cookie parameters belong to the group's headers
        if not _HOLE_NAME.match(name):
            warnings.append(f"{key}: parameter {name!r} cannot be a template argument; left out")
            if where == "path":
                return None
            continue
        prop = dict(param.get("schema") or {"type": "string"})
        if isinstance(param.get("description"), str):
            prop.setdefault("description", param["description"])
        properties[name] = prop
        if where == "path" or param.get("required"):
            required.append(name)
        if where == "query":
            query.append(f"{name}={{{name}}}")
    body_schema, body_required = _json_body_schema(op.get("requestBody"))
    body_template: str | None = None
    if body_schema is not None:
        arg = "body" if "body" not in properties else "request_body"
        properties[arg] = body_schema
        if body_required:
            required.append(arg)
        body_template = "{" + arg + "}"
    elif isinstance(op.get("requestBody"), dict):
        warnings.append(f"{key}: a request body that is not JSON is left out")
    summary = op.get("summary") if isinstance(op.get("summary"), str) else None
    detail = op.get("description") if isinstance(op.get("description"), str) else None
    description = "\n\n".join(p for p in (summary, detail) if p)[:4000]
    template = path + ("?" + "&".join(query) if query else "")
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = sorted(set(required))
    try:
        tool = HttpApiTool(
            name=_tool_name(op.get("operationId"), method, path, taken),
            description=description,
            method=method,  # type: ignore[arg-type]
            path=template,
            body_template=body_template,
            input_schema=schema,
            operation=key,
        )
    except ValidationError as e:
        warnings.append(f"{key}: left out ({e.errors()[0].get('msg', 'invalid')})")
        return None
    return DraftOperation(key=key, tool=tool, summary=summary)


def read_openapi(
    doc: Any, *, source_url: str | None = None, taken_names: set[str] | None = None
) -> OpenApiReading:
    """Every operation of ``doc`` as a draft tool, with the suggested group settings."""
    if not isinstance(doc, dict) or not str(doc.get("openapi", "")).startswith("3."):
        raise OpenApiError("not an OpenAPI 3.0 or 3.1 document (no 'openapi: 3.x' field)")
    resolved = _resolve(doc, doc)
    paths = resolved.get("paths") or {}
    if not isinstance(paths, dict):
        raise OpenApiError("the document's 'paths' is not an object")
    info = resolved.get("info") if isinstance(resolved.get("info"), dict) else {}
    taken = set(taken_names or ())
    warnings: list[str] = []
    operations: list[DraftOperation] = []
    for path, item in paths.items():
        if not isinstance(item, dict) or not isinstance(path, str) or not path.startswith("/"):
            continue
        for method in HTTP_METHODS:
            op = item.get(method.lower())
            if isinstance(op, dict):
                draft = _operation(method, path, item, op, taken, warnings)
                if draft is not None:
                    operations.append(draft)
    header, prefix = _auth(resolved)
    return OpenApiReading(
        title=info.get("title") if isinstance(info.get("title"), str) else None,
        version=str(info["version"]) if info.get("version") is not None else None,
        base_url=_base_url(resolved, source_url),
        auth_header=header,
        auth_prefix=prefix,
        operations=operations,
        warnings=warnings,
    )


@dataclass(frozen=True)
class ReimportPlan:
    added: list[DraftOperation]
    removed: list[str]  # tool names
    kept: list[str]  # tool names


def plan_reimport(transport: HttpApiTransport, reading: OpenApiReading) -> ReimportPlan:
    """What applying ``reading`` would change; changes nothing (spec: preview first)."""
    in_doc = reading.by_key()
    known = {t.operation for t in transport.tools if t.operation} | set(
        transport.source.skipped if transport.source else []
    )
    added = [op for key, op in in_doc.items() if key not in known]
    removed = [t.name for t in transport.tools if t.operation and t.operation not in in_doc]
    kept = [t.name for t in transport.tools if t.name not in removed]
    return ReimportPlan(added=added, removed=removed, kept=kept)


def apply_reimport(
    transport: HttpApiTransport,
    reading: OpenApiReading,
    *,
    add_keys: set[str],
    fetched_at: datetime,
) -> HttpApiTransport:
    """The group after a re-import: removed tools gone, chosen additions on,
    kept tools' requests refreshed with their switch and flag kept."""
    plan = plan_reimport(transport, reading)
    in_doc = reading.by_key()
    removed = set(plan.removed)
    taken = {t.name for t in transport.tools if t.name not in removed}
    tools: list[HttpApiTool] = []
    for tool in transport.tools:
        if tool.name in removed:
            continue
        fresh = in_doc.get(tool.operation) if tool.operation else None
        if fresh is None:
            tools.append(tool)
            continue
        tools.append(
            fresh.tool.model_copy(
                update={
                    "name": tool.name,
                    "enabled": tool.enabled,
                    "changes_data": tool.changes_data,
                    "headers": tool.headers or fresh.tool.headers,
                }
            )
        )
    skipped: list[str] = []
    for op in plan.added:
        if op.key in add_keys:
            name = (
                op.tool.name
                if op.tool.name not in taken
                else _tool_name(op.tool.name + "_new", op.tool.method, op.tool.path, taken)
            )
            taken.add(name)
            tools.append(op.tool.model_copy(update={"name": name, "enabled": True}))
        else:
            skipped.append(op.key)
    still_skipped = [
        k for k in (transport.source.skipped if transport.source else []) if k in in_doc
    ]
    source = OpenApiSource(
        kind=transport.source.kind if transport.source else "file",
        location=transport.source.location if transport.source else "openapi",
        title=reading.title,
        version=reading.version,
        fetched_at=fetched_at,
        skipped=sorted(set(still_skipped) | set(skipped)),
    )
    return transport.model_copy(update={"tools": tools, "source": source})


__all__ = [
    "DraftOperation",
    "OpenApiError",
    "OpenApiReading",
    "ReimportPlan",
    "apply_reimport",
    "plan_reimport",
    "read_openapi",
]
