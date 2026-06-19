"""Map official MCP Registry server entries to Coffer config drafts (ADR-029).

Pure domain logic — no I/O. The registry (``registry.modelcontextprotocol.io``)
is a **preview** API whose entries carry optional/variable fields, so every
field access here is defensive. A registry ``server`` entry wraps one or more
``packages`` (downloadable run configs) and/or ``remotes`` (hosted HTTP/SSE
endpoints). We turn the first usable one into a draft the Add-MCP-server flow
can pre-fill.

Key robustness rule: ``packages[].runtimeHint`` is frequently absent, so the run
command is inferred from ``packages[].registryType`` (npm→npx, pypi→uvx,
oci→docker, nuget→dnx). cargo/mcpb have no canonical launcher → not auto-
installable (the entry is still shown, with ``draft = None``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.domain.error_base import CofferError


class RegistryUnavailable(CofferError):  # noqa: N818
    """The official MCP Registry could not be reached (network / timeout / 5xx).

    Surfaces map this to 502; the Add-MCP-server paste-JSON path stays usable."""

    code = "REGISTRY_UNAVAILABLE"


# registryType → local launcher command, used when runtimeHint is missing.
_LAUNCHER_BY_REGISTRY_TYPE: dict[str, str] = {
    "npm": "npx",
    "pypi": "uvx",
    "oci": "docker",
    "nuget": "dnx",
}


@dataclass(frozen=True)
class RegistryEnvVar:
    """A declared environment variable / header the user must supply a value for."""

    key: str
    is_secret: bool
    required: bool
    description: str | None


@dataclass(frozen=True)
class RegistryDraft:
    """A ready-to-edit config draft. ``env`` values are NOT provided (the user
    fills them); secret-flagged ones become credential refs at registration."""

    transport_type: str  # "stdio" | "http"
    command: str  # launcher for stdio; "" for http
    args: tuple[str, ...]
    url: str  # endpoint for http; "" for stdio
    env: tuple[RegistryEnvVar, ...]


@dataclass(frozen=True)
class RegistryServer:
    """A normalized registry search result."""

    name: str
    title: str | None
    description: str
    version: str | None
    registry_type: str | None
    transport_type: str  # "stdio" | "http"
    installable: bool
    homepage: str | None
    draft: RegistryDraft | None


def map_registry_entry(item: Any) -> RegistryServer | None:
    """Normalize one list item (``{"server": {...}, "_meta": {...}}``) or a bare
    ``server`` dict. Returns ``None`` for an entry without a usable name."""
    server = item.get("server") if isinstance(item, dict) else None
    if not isinstance(server, dict):
        # Tolerate a bare server object (some shapes nest, some don't).
        server = item if isinstance(item, dict) and "name" in item else None
    if not isinstance(server, dict):
        return None
    name = server.get("name")
    if not isinstance(name, str) or not name:
        return None

    packages_raw = server.get("packages")
    packages = packages_raw if isinstance(packages_raw, list) else []
    remotes_raw = server.get("remotes")
    remotes = remotes_raw if isinstance(remotes_raw, list) else []

    registry_type: str | None = None
    transport_type = "stdio"
    draft: RegistryDraft | None = None

    pkg = _first_package(packages)
    if pkg is not None:
        rt = pkg.get("registryType")
        registry_type = rt if isinstance(rt, str) else None
        draft = _package_draft(pkg)
        if draft is not None:
            transport_type = draft.transport_type
    if draft is None:
        remote_draft = _remote_draft(_first_remote(remotes))
        if remote_draft is not None:
            transport_type = "http"
            registry_type = None  # the draft is the remote endpoint, not the package
            draft = remote_draft

    return RegistryServer(
        name=name,
        title=server.get("title") if isinstance(server.get("title"), str) else None,
        description=str(server.get("description") or ""),
        version=server.get("version") if isinstance(server.get("version"), str) else None,
        registry_type=registry_type,
        transport_type=transport_type,
        installable=draft is not None,
        homepage=_homepage(server),
        draft=draft,
    )


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #


def _first_package(packages: list[Any]) -> dict[str, Any] | None:
    for p in packages:
        if isinstance(p, dict):
            return p
    return None


def _first_remote(remotes: list[Any]) -> dict[str, Any] | None:
    for r in remotes:
        if isinstance(r, dict):
            return r
    return None


def _homepage(server: dict[str, Any]) -> str | None:
    website = server.get("websiteUrl")
    if isinstance(website, str) and website:
        return website
    repo = server.get("repository")
    if isinstance(repo, dict):
        url = repo.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _package_draft(pkg: dict[str, Any]) -> RegistryDraft | None:
    transport_raw = pkg.get("transport")
    transport = transport_raw if isinstance(transport_raw, dict) else {}
    ttype = transport.get("type")
    if ttype in ("streamable-http", "sse"):
        url = transport.get("url")
        if isinstance(url, str) and url:
            return RegistryDraft("http", "", (), url, _env_vars(pkg))
        return None  # http package without a url is not usable

    # stdio (or an unspecified type — assume stdio, the common case).
    rtype = pkg.get("registryType")
    hint = pkg.get("runtimeHint")
    launcher = (
        hint if isinstance(hint, str) and hint else _LAUNCHER_BY_REGISTRY_TYPE.get(rtype or "")
    )
    identifier = pkg.get("identifier")
    if not launcher or not isinstance(identifier, str) or not identifier:
        return None  # cargo/mcpb/unknown, or no package id → not auto-installable

    env = _env_vars(pkg)
    runtime_args = _render_args(pkg.get("runtimeArguments"))
    package_args = _render_args(pkg.get("packageArguments"))
    args = _assemble_args(launcher, identifier, pkg.get("version"), runtime_args, package_args, env)
    return RegistryDraft("stdio", launcher, tuple(args), "", env)


def _assemble_args(
    launcher: str,
    identifier: str,
    version: Any,
    runtime_args: list[str],
    package_args: list[str],
    env: tuple[RegistryEnvVar, ...],
) -> list[str]:
    """Build the launcher argv: runtime/container args, then the package ref,
    then the server program's own args. Launcher-specific shaping included."""
    ver = version if isinstance(version, str) and version else None
    if launcher == "docker":
        # The image ref (identifier) already includes host + tag. `-i` keeps
        # stdin open for the stdio transport; `--rm` cleans up on exit. Each
        # declared env var is forwarded into the container with `-e <key>`
        # (Coffer sets the value on the docker CLI process; without `-e` it would
        # never reach the MCP server running inside the container).
        env_flags = [tok for e in env for tok in ("-e", e.key)]
        head = ["run", "-i", "--rm", *env_flags, *runtime_args]
        return [*head, identifier, *package_args]
    if launcher == "npx":
        ref = f"{identifier}@{ver}" if ver else identifier
        args = list(runtime_args)
        if "-y" not in args and "--yes" not in args:
            args.insert(0, "-y")
        return [*args, ref, *package_args]
    # uvx / dnx / any other launcher: runtime args, the bare identifier, then
    # program args. Version pinning syntax varies per launcher, so we don't pin.
    return [*runtime_args, identifier, *package_args]


def _render_args(raw: Any) -> list[str]:
    """Render registry argument objects to concrete strings, skipping any with
    unresolved ``{template}`` placeholders (the user can edit those after)."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        raw_value = a.get("value")
        if not isinstance(raw_value, str) or not raw_value:
            raw_value = a.get("default")
        value = (
            raw_value if isinstance(raw_value, str) and raw_value and "{" not in raw_value else None
        )
        if a.get("type") == "named":
            name = a.get("name")
            if isinstance(name, str) and name:
                out.append(name)
                if value is not None and value != name:  # avoid `--flag --flag`
                    out.append(value)
        elif value is not None:
            out.append(value)
    return out


def _env_vars(pkg: dict[str, Any]) -> tuple[RegistryEnvVar, ...]:
    raw = pkg.get("environmentVariables")
    if not isinstance(raw, list):
        headers = pkg.get("headers")
        raw = headers if isinstance(headers, list) else []
    out: list[RegistryEnvVar] = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        key = e.get("name")
        if not isinstance(key, str) or not key:
            continue
        desc = e.get("description")
        out.append(
            RegistryEnvVar(
                key=key,
                is_secret=bool(e.get("isSecret")),
                required=bool(e.get("isRequired")),
                description=desc if isinstance(desc, str) else None,
            )
        )
    return tuple(out)


def _remote_draft(remote: dict[str, Any] | None) -> RegistryDraft | None:
    if remote is None:
        return None
    url = remote.get("url")
    if not isinstance(url, str) or not url:
        return None
    return RegistryDraft("http", "", (), url, _env_vars(remote))
