"""Enumerate what a plugin package contributes, with each component's description.

Backs the per-plugin detail read (spec agent-registry "Read one installed
plugin's detail read-only"). Given the directory a plugin's manifest sits in,
reads the package's default component locations:

- ``skills/<name>/SKILL.md`` — one skill per folder, described by its frontmatter;
- ``commands/*.md`` — one slash command per file, described by its frontmatter;
- ``agents/*.md`` — one subagent per file, named and described by its frontmatter;
- ``hooks/hooks.json`` — the hook event names it registers handlers for;
- ``.mcp.json`` — the MCP server names it bundles.

Read-only and best-effort like the rest of ``plugin_bundle``: a missing folder,
an unreadable file or malformed frontmatter yields an empty tuple or a
component without a description, never an exception.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import yaml

from coffer.domain.agent.plugin_bundle import PluginComponent, PluginContents, PluginPart

_FENCE = "---"


def read_plugin_contents(root: pathlib.Path) -> PluginContents:
    return PluginContents(
        root=str(root),
        skills=_skills(root / "skills"),
        commands=_markdown_components(root / "commands", named_by_frontmatter=False),
        agents=_markdown_components(root / "agents", named_by_frontmatter=True),
        hooks=_hook_events(root / "hooks" / "hooks.json"),
        mcp_servers=_mcp_servers(root / ".mcp.json"),
    )


def _frontmatter(path: pathlib.Path) -> dict[str, Any]:
    """The file's leading ``---``-fenced YAML block, or ``{}``."""
    try:
        text = path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith(_FENCE):
        return {}
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].rstrip() == _FENCE:
            try:
                loaded = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
    return {}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _skills(path: pathlib.Path) -> tuple[PluginComponent, ...]:
    try:
        dirs = [p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return ()
    return tuple(
        sorted(
            (
                PluginComponent(
                    name=d.name,
                    description=_text(_frontmatter(d / "SKILL.md").get("description")),
                )
                for d in dirs
            ),
            key=lambda c: c.name,
        )
    )


def _markdown_files(
    path: pathlib.Path, *, named_by_frontmatter: bool
) -> list[tuple[pathlib.Path, PluginComponent]]:
    """Every ``*.md`` file of ``path`` with its component. A subagent is known
    by its frontmatter ``name`` (falling back to the file stem); a command by
    its file stem, which is what the user types after the slash."""
    try:
        files = [p for p in path.iterdir() if p.is_file() and p.suffix == ".md"]
    except OSError:
        return []
    out: list[tuple[pathlib.Path, PluginComponent]] = []
    for f in files:
        fm = _frontmatter(f)
        name = (_text(fm.get("name")) if named_by_frontmatter else None) or f.stem
        out.append((f, PluginComponent(name=name, description=_text(fm.get("description")))))
    return out


def _markdown_components(
    path: pathlib.Path, *, named_by_frontmatter: bool
) -> tuple[PluginComponent, ...]:
    pairs = _markdown_files(path, named_by_frontmatter=named_by_frontmatter)
    return tuple(sorted((c for _f, c in pairs), key=lambda c: c.name))


def find_skill(root: pathlib.Path, name: str) -> PluginComponent | None:
    """The plugin's ``skills/<name>/`` component, or ``None``. Matches against
    the folders the package really holds, so ``name`` never builds a path."""
    return next((c for c in _skills(root / "skills") if c.name == name), None)


def find_markdown(root: pathlib.Path, kind: str, name: str) -> tuple[str, PluginComponent] | None:
    """``(path relative to root, component)`` of the command (``commands``) or
    subagent (``agents``) called ``name``, or ``None``."""
    for f, comp in _markdown_files(root / kind, named_by_frontmatter=kind == "agents"):
        if comp.name == name:
            return f"{kind}/{f.name}", comp
    return None


def read_mcp_server(root: pathlib.Path, name: str) -> dict[str, Any] | None:
    """The ``.mcp.json`` entry of server ``name`` exactly as written, or ``None``."""
    data = _load_json(root / ".mcp.json")
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    entry = servers.get(name) if isinstance(servers, dict) else None
    return entry if isinstance(entry, dict) else None


def _load_json(path: pathlib.Path) -> object:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _hook_events(path: pathlib.Path) -> tuple[str, ...]:
    data = _load_json(path)
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if isinstance(hooks, dict):
        return tuple(sorted(str(k) for k in hooks))
    return ()


def _mcp_servers(path: pathlib.Path) -> tuple[str, ...]:
    data = _load_json(path)
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if isinstance(servers, dict):
        return tuple(sorted(str(k) for k in servers))
    return ()


def find_part(root: pathlib.Path, kind: str, name: str) -> PluginPart | None:
    """Resolve one skill / command / subagent / MCP server of the package at
    ``root`` by name; ``None`` when the package holds no such thing."""
    if kind == "skills":
        skill = find_skill(root, name)
        return (
            PluginPart(kind, name, str(root), f"skills/{name}", skill.description)
            if skill
            else None
        )
    if kind in ("commands", "agents"):
        found = find_markdown(root, kind, name)
        return PluginPart(kind, name, str(root), found[0], found[1].description) if found else None
    if kind == "mcp-servers":
        config = read_mcp_server(root, name)
        return PluginPart(kind, name, str(root), ".mcp.json", config=config) if config else None
    return None
