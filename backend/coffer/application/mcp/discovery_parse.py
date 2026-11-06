"""Turn an upstream's ``*/list`` answer into Coffer's capability models.

``config_hash`` fingerprints the server config a list was taken under, so a
list saved under another config is known to be stale (ADR
session-subprocess-model).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from coffer.domain.mcp.capability import MCPPrompt, MCPPromptArgument, MCPResource, MCPTool


def _output_schema_of(tool: Any) -> dict[str, Any] | None:
    """An upstream tool's declared ``outputSchema`` as declared, or None."""
    raw = getattr(tool, "output_schema", None)
    return dict(raw) if isinstance(raw, dict) and raw else None


def _annotations_of(tool: Any) -> dict[str, Any] | None:
    """An upstream tool's MCP annotations in their wire spelling, or None."""
    raw = getattr(tool, "annotations", None)
    if raw is None:
        return None
    if hasattr(raw, "model_dump"):
        dumped: dict[str, Any] = raw.model_dump(exclude_none=True, by_alias=True, mode="json")
        return dumped or None
    return dict(raw) if isinstance(raw, dict) and raw else None


def config_hash(config: dict[str, Any]) -> str:
    """A server config's fingerprint: a list saved under another one is stale."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_tools(result: Any) -> list[MCPTool]:
    return [
        MCPTool(
            name=t.name,
            description=getattr(t, "description", None),
            input_schema=getattr(t, "input_schema", None) or {},
            annotations=_annotations_of(t),
            output_schema=_output_schema_of(t),
        )
        for t in getattr(result, "tools", [])
    ]


def parse_resources(result: Any) -> list[MCPResource]:
    return [
        MCPResource(
            uri=str(getattr(r, "uri", "")),
            name=getattr(r, "name", None),
            description=getattr(r, "description", None),
            mime_type=getattr(r, "mime_type", None),
        )
        for r in getattr(result, "resources", [])
    ]


def parse_prompts(result: Any) -> list[MCPPrompt]:
    return [
        MCPPrompt(
            name=p.name,
            description=getattr(p, "description", None),
            arguments=[
                MCPPromptArgument(
                    name=a.name,
                    description=getattr(a, "description", None),
                    required=getattr(a, "required", False),
                )
                for a in (getattr(p, "arguments", []) or [])
            ],
        )
        for p in getattr(result, "prompts", [])
    ]
