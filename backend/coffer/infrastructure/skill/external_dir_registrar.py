"""Register / deregister a Coffer-owned external skill directory in an agent's
YAML config file (spec 005, EXTERNAL_DIR delivery — Hermes).

The agent (e.g. Hermes) scans a list of external directories declared under a
nested key in its config file (``skills.external_dirs``). Coffer folder-delivers
the enabled skills into a Coffer-owned directory and registers that directory
here so the agent picks them up.

Design notes:
- Round-trip YAML (``ruamel``) so the user's comments / ordering / quoting in
  the rest of the file survive an edit — mirrors ``mcp_entries`` for the MCP
  case. A self-contained handler lives here because the skill layer must not
  import ``coffer.domain.agent`` (Contract 5).
- Idempotent: registering an already-present directory is a no-op; entries are
  de-duplicated by their resolved filesystem path so ``~`` and absolute forms
  collapse. Deregistering the last entry removes the now-empty list (and an
  emptied container map) to avoid leaving dangling scaffolding.
- Defensive: a missing/empty/comment-only file registers cleanly; a malformed
  file or non-mapping container is left untouched rather than clobbered.
"""

from __future__ import annotations

import io
import logging
import pathlib
from collections.abc import MutableMapping, MutableSequence
from typing import Any

from ruamel.yaml import YAML

from coffer.domain.skill.external_dir import ExternalDirRegistration

log = logging.getLogger(__name__)


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _resolved(path: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(path).expanduser().resolve()


class YamlExternalDirRegistrar:
    """Adapter implementing ``ExternalDirRegistrarPort`` for YAML config files."""

    def register(self, reg: ExternalDirRegistration) -> None:
        """Ensure ``reg.external_dir`` is listed at ``reg.container_keys``.

        Creates the config file (and parents) and any missing intermediate
        mappings. A no-op if the directory is already registered.
        """
        if not reg.container_keys:
            return
        data = self._load(reg.config_path)
        if data is None:
            return  # malformed file — never clobber

        container = self._ensure_container(data, reg.container_keys[:-1])
        if container is None:
            return  # an intermediate node is not a mapping — leave it alone
        list_key = reg.container_keys[-1]
        existing = container.get(list_key)
        if existing is None:
            existing = []
            container[list_key] = existing
        if not isinstance(existing, MutableSequence):
            return  # the key holds a non-list — don't overwrite user content

        target = _resolved(reg.external_dir)
        if any(_resolved(str(e)) == target for e in existing):
            return  # already registered
        existing.append(str(reg.external_dir))
        self._dump(reg.config_path, data)

    def deregister(self, reg: ExternalDirRegistration) -> None:
        """Remove ``reg.external_dir`` from ``reg.container_keys``.

        No-op if the file, the container path, or the entry is absent. Prunes
        an emptied list (and an emptied container mapping) so removing the last
        skill leaves no dangling registration.
        """
        if not reg.container_keys or not reg.config_path.exists():
            return
        data = self._load(reg.config_path)
        if data is None:
            return

        # Walk to the list's container without creating anything.
        container: Any = data
        for key in reg.container_keys[:-1]:
            nxt = container.get(key) if isinstance(container, MutableMapping) else None
            if not isinstance(nxt, MutableMapping):
                return  # path absent — nothing to remove
            container = nxt
        if not isinstance(container, MutableMapping):
            return
        list_key = reg.container_keys[-1]
        existing = container.get(list_key)
        if not isinstance(existing, MutableSequence):
            return

        target = _resolved(reg.external_dir)
        kept = [e for e in existing if _resolved(str(e)) != target]
        if len(kept) == len(existing):
            return  # nothing matched
        if kept:
            container[list_key] = kept
        else:
            del container[list_key]
            # Prune an emptied container mapping (e.g. a now-empty ``skills:``)
            # only when we created the chain solely for this registration.
            self._prune_empty_chain(data, reg.container_keys[:-1])
        self._dump(reg.config_path, data)

    # ----- helpers -----

    def _load(self, path: pathlib.Path) -> MutableMapping[str, Any] | None:
        """Return the parsed top-level mapping, an empty map for missing/empty
        files, or ``None`` for malformed / non-mapping content (caller skips)."""
        if not path.exists():
            return _yaml().load("") or {}
        try:
            text = path.read_text(encoding="utf-8")
            data = _yaml().load(text)
        except Exception:
            log.warning("external_dir_registrar: cannot parse %s; leaving untouched", path)
            return None
        if data is None:
            return {}
        if not isinstance(data, MutableMapping):
            log.warning("external_dir_registrar: %s top-level is not a mapping; skipping", path)
            return None
        return data

    def _dump(self, path: pathlib.Path, data: MutableMapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        _yaml().dump(data, buf)
        path.write_text(buf.getvalue(), encoding="utf-8")

    def _ensure_container(
        self, data: MutableMapping[str, Any], keys: tuple[str, ...]
    ) -> MutableMapping[str, Any] | None:
        node: MutableMapping[str, Any] = data
        for key in keys:
            child = node.get(key)
            if child is None:
                child = {}
                node[key] = child
            if not isinstance(child, MutableMapping):
                return None
            node = child
        return node

    def _prune_empty_chain(self, data: MutableMapping[str, Any], keys: tuple[str, ...]) -> None:
        if not keys:
            return
        # Re-walk to find the deepest empty mapping and drop it.
        chain: list[tuple[MutableMapping[str, Any], str]] = []
        node: Any = data
        for key in keys:
            if not isinstance(node, MutableMapping) or key not in node:
                return
            chain.append((node, key))
            node = node[key]
        for parent, key in reversed(chain):
            child = parent.get(key)
            if isinstance(child, MutableMapping) and not child:
                del parent[key]
            else:
                break
