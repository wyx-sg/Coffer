"""The command line's groups, created once and shared by every command module.

A command module asks for its group by path (``group("custom-tool env")``);
the group is created on first use, under its parent, with the help text below.
The hand-written modules that predate this (``daemon``, ``secret``…) hand their
own Typer app over with :func:`adopt`, so declared commands land in the same
group as theirs.
"""

from __future__ import annotations

import typer

#: Help per group path: what a person or agent manages there.
GROUP_HELP: dict[str, str] = {
    "agent": "Manage coding agents: add, connect, their MCP entries, plugins and sessions.",
    "agent mcp-entry": "An agent's own MCP entries: list, show, adopt into Coffer, remove.",
    "agent mcp-import": "Import MCP servers found in agents' configs into Coffer.",
    "agent plugin": "An agent's plugins: list, show, switch on or off, uninstall.",
    "agent session": "An agent's native sessions: list, rename, delete.",
    "agent unmanaged-skill": "Skills an agent holds that Coffer does not manage.",
    "agent native-memory": "What an agent keeps in its own memory files (read-only).",
    "app": "The Coffer desktop app.",
    "app update": "Check for, and install, a new version of the desktop app.",
    "approval": "Secret approvals: list, show, approve with Touch ID, reject.",
    "attention": "What needs you (the Overview list): list, ignore, un-ignore.",
    "channel": "Messaging channels: status, pairing, people, notify, restart.",
    "cli": "Command-line tools Coffer manages for skills.",
    "config": "Daemon settings read before it binds (work while it is down).",
    "conversation": "Conversations: rename, stop a turn, delete (list: agent session all).",
    "custom-tool": "Custom tools: groups of HTTP API requests served as MCP tools.",
    "custom-tool group": "Custom-tool groups: create, show, change, delete, switch, reach.",
    "custom-tool tool": "One custom tool: add, show, change, switch, test, delete.",
    "custom-tool env": "A group's environments: base URL, headers, secrets, variables.",
    "custom-tool import": "Read an OpenAPI document into draft tools.",
    "custom-tool reimport": "Preview and apply a re-import of a group's OpenAPI document.",
    "daemon": "The Coffer daemon: start, stop, status, and its settings.",
    "knowledge": "Knowledge collections (documents are plain files you edit directly).",
    "log": "Read Coffer's audit, MCP and daemon logs.",
    "mcp": "MCP servers: register, change, test, their tools and logs.",
    "memory": "Memory partitions (notes are plain files you edit directly).",
    "model": "Ask a model endpoint which models it serves, or test it.",
    "path": "Where Coffer keeps files you read directly.",
    "provider": "Model providers: connections, prices, switching agents' models.",
    "proxy": "The local model proxy.",
    "resource": "Any resource by uid: show, rename, switch on or off, reach, delete.",
    "secret": "Secrets: list, store, delete, reveal in the app, import, approvals.",
    "settings": "Settings: approvals, secret storage, features, data, upkeep.",
    "skill": "Skills: import, update, delivery to agents, sources.",
    "sync": "Vault sync: remote, rounds, machines, conflicts.",
    "usage": "Model usage and cost.",
    "vault": "The vault's history and the hand edits it refused.",
    # Nested groups.
    "channel pairing": "Pair a person with a channel by a code they send the bot.",
    "channel person": "The people paired with a channel.",
    "daemon port": "The port the daemon's next start uses.",
    "daemon residency": "Whether the daemon starts at login.",
    "mcp tool": "Switch a server's tools, prompts and resources on or off.",
    "provider price-list": "The bundled model price list.",
    "provider switch": "Switch an agent type's model to a connection: preview, then apply.",
    "resource reach": "Which agents a resource reaches.",
    "secret local-access": "Hand a standalone secret to programs `coffer run` starts.",
    "settings approvals": "Whether a secret going somewhere new waits for approval.",
    "settings engine": "Coffer's own model: transcription and upkeep passes.",
    "settings feature": "Switch one experimental feature on this machine.",
    "settings retention": "How long each log is kept.",
    "settings secrets": "Where the master key is kept.",
    "settings storage": "What Coffer stores, and clearing its caches.",
    "skill copy": "An agent's copy of a skill that differs from the master.",
    "skill orphan": "Folders in the skills store that no skill owns.",
    "skill source": "Where a skill came from: check, change, merge updates.",
    "skill update-check": "How often skills' sources are checked for updates.",
    "sync key": "The master key, as sync moves it between machines (never shown).",
    "sync machine": "One machine of the vault: rename, retire, restore.",
    "sync remote": "The git remote the vault syncs with.",
}

_GROUPS: dict[str, typer.Typer] = {}
_ROOT: typer.Typer | None = None


def set_root(root: typer.Typer) -> None:
    global _ROOT
    _ROOT = root


def adopt(path: str, app: typer.Typer) -> typer.Typer:
    """Make an existing Typer app the group at ``path``."""
    _GROUPS[path] = app
    _attach(path, app)
    return app


def _attach(path: str, app: typer.Typer) -> None:
    parent, _, name = path.rpartition(" ")
    if parent:
        group(parent).add_typer(app, name=name, help=GROUP_HELP.get(path))
    else:
        assert _ROOT is not None, "set_root() first"
        _ROOT.add_typer(app, name=name, help=GROUP_HELP.get(path))


def group(path: str) -> typer.Typer:
    """The group at ``path`` (``""`` is the root), created on first use."""
    if path == "":
        assert _ROOT is not None, "set_root() first"
        return _ROOT
    found = _GROUPS.get(path)
    if found is not None:
        return found
    app = typer.Typer(help=GROUP_HELP.get(path), no_args_is_help=True)
    _GROUPS[path] = app
    _attach(path, app)
    return app


__all__ = ["GROUP_HELP", "adopt", "group", "set_root"]
