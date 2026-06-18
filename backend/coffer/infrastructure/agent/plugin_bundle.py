"""Filesystem reader for a plugin's manifest + bundled components.

Given a plugin's install location, reads its manifest
(``.claude-plugin/plugin.json`` for Claude plugins, ``.codex-plugin/plugin.json``
for Codex plugins) for version / description / author / homepage and enumerates
the plugin's bundled ``skills/`` (subfolders), ``commands/`` (``*.md`` files),
and ``.mcp.json`` (``mcpServers`` keys).

The install location may be either the exact version directory (Claude records
``installPath`` directly) or the ``<marketplace>/<name>`` parent whose single
child is the version directory (Codex does not record a path, so the service
passes the cache parent and this reader descends into the version subdir).

Every read is **read-only and best-effort**: a missing directory, absent
manifest, or malformed JSON yields ``None`` / empty tuples rather than raising —
the agent plugin listing must never fail because one plugin package is
incomplete. This adapter implements the ``PluginDetailReader`` Protocol the
application's :class:`AgentPluginService` depends on.
"""

from __future__ import annotations

import json
import pathlib
import re

from coffer.domain.agent.plugin_bundle import PluginDetail

# Manifest locations, in priority order — a plugin carries exactly one.
_MANIFEST_RELPATHS = (
    pathlib.Path(".claude-plugin") / "plugin.json",
    pathlib.Path(".codex-plugin") / "plugin.json",
)

_VERSION_NUMS = re.compile(r"\d+")


def _version_sort_key(path: pathlib.Path) -> tuple[bool, tuple[int, ...], str]:
    """Sort key for version subdirs: numeric version order, newest highest.

    Compares the numeric components of the dir name as integers (so "26.1"
    ranks above "9.0", which a plain string sort gets wrong), with the raw name
    as a final tiebreak. Names with no digits sort below versioned ones. Used
    with ``reverse=True`` so the highest version wins. Dependency-free on
    purpose — this is core daemon code that must not import optional packages.
    """
    nums = tuple(int(n) for n in _VERSION_NUMS.findall(path.name))
    return (bool(nums), nums, path.name)


class FsPluginDetailReader:
    """Reads a plugin's manifest + bundled components from its install dir."""

    def read(self, install_path: str) -> PluginDetail | None:
        if not install_path:
            return None
        root = self._resolve_root(pathlib.Path(install_path))
        if root is None:
            return None
        version, description, author, homepage = self._manifest(root)
        return PluginDetail(
            version=version,
            description=description,
            author=author,
            homepage=homepage,
            skills=self._subdir_names(root / "skills"),
            commands=self._command_names(root / "commands"),
            mcp_servers=self._mcp_server_names(root / ".mcp.json"),
        )

    @classmethod
    def _resolve_root(cls, path: pathlib.Path) -> pathlib.Path | None:
        """Return the directory that holds the plugin's manifest.

        Handles both shapes: the manifest sitting directly under ``path``
        (Claude's recorded install dir), or one level down in a version subdir
        (Codex, where the service passes the ``<marketplace>/<name>`` parent).
        Falls back to ``path`` itself so bundle enumeration still runs when no
        manifest is present.
        """
        if not path.is_dir():
            return None
        if cls._has_manifest(path):
            return path
        try:
            # Newest version first: Codex caches name dirs by version
            # (`<name>/<version>/`), so prefer the highest version that carries a
            # manifest — a plain string sort would rank "9.0" above "26.1".
            subdirs = sorted(
                (c for c in path.iterdir() if c.is_dir()), key=_version_sort_key, reverse=True
            )
        except OSError:
            return path
        for child in subdirs:
            if cls._has_manifest(child):
                return child
        return path

    @staticmethod
    def _has_manifest(d: pathlib.Path) -> bool:
        return any((d / rel).is_file() for rel in _MANIFEST_RELPATHS)

    @classmethod
    def _manifest(cls, root: pathlib.Path) -> tuple[str | None, str | None, str | None, str | None]:
        """Return ``(version, description, author_name, homepage)`` from the manifest."""
        data: object = None
        for rel in _MANIFEST_RELPATHS:
            try:
                data = json.loads((root / rel).read_text("utf-8"))
                break
            except (OSError, ValueError):
                continue
        if not isinstance(data, dict):
            return None, None, None, None

        version = data.get("version")
        description = data.get("description")
        # ``author`` may be a bare string or an object with a ``name`` field.
        author_raw = data.get("author")
        author: str | None = None
        if isinstance(author_raw, dict):
            name = author_raw.get("name")
            author = str(name) if name else None
        elif isinstance(author_raw, str):
            author = author_raw or None
        # Prefer the canonical homepage, fall back to the repository URL.
        homepage = data.get("homepage") or data.get("repository")

        return (
            str(version) if version else None,
            str(description) if description else None,
            author,
            str(homepage) if homepage else None,
        )

    @staticmethod
    def _subdir_names(path: pathlib.Path) -> tuple[str, ...]:
        try:
            return tuple(
                sorted(p.name for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))
            )
        except OSError:
            return ()

    @staticmethod
    def _command_names(path: pathlib.Path) -> tuple[str, ...]:
        try:
            return tuple(
                sorted(p.stem for p in path.iterdir() if p.is_file() and p.suffix == ".md")
            )
        except OSError:
            return ()

    @staticmethod
    def _mcp_server_names(path: pathlib.Path) -> tuple[str, ...]:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return ()
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if isinstance(servers, dict):
            return tuple(sorted(str(k) for k in servers))
        return ()
