"""``NativeConfigModelDiscovery`` — read an agent's own config for extra models.

The CLIs already keep a machine-readable record of the models they can be put
on: Claude Code caches the extra options its picker offers in ``.claude.json``,
and Codex's ``config.toml`` names the model each profile runs. Reading them is
how a model that shipped after this release still reaches Coffer's picker.

Best-effort by contract (``ModelDiscoveryPort``): every failure is an empty
list. A missing file is the ordinary case — the user may simply never have
opened that CLI — so it is not even logged.
"""

from __future__ import annotations

import json
import logging
import pathlib
import tomllib
from typing import Any

from coffer.domain.agent.model_catalogue import AgentModel

_log = logging.getLogger(__name__)

#: Claude Code's cache of the extra model options its own picker offers, e.g.
#: ``[{"value": "claude-fable-5-1[1m]", "label": "Fable", "description": "…"}]``.
_CLAUDE_CACHE_KEY = "additionalModelOptionsCache"


class NativeConfigModelDiscovery:
    """``ModelDiscoveryPort`` backed by the agent's native config file."""

    def discover(self, *, agent_key: str, config_dir: pathlib.Path) -> list[AgentModel]:
        if agent_key == "claude_code":
            return self._claude_code(config_dir)
        if agent_key == "codex":
            return self._codex(config_dir)
        return []

    # --- claude code ---------------------------------------------------------

    def _claude_code(self, config_dir: pathlib.Path) -> list[AgentModel]:
        """Claude Code keeps ``.claude.json`` NEXT TO its config dir in the
        default layout (``~/.claude`` + ``~/.claude.json``) but INSIDE it when
        ``CLAUDE_CONFIG_DIR`` points elsewhere — try inside first, so a user's
        explicit override wins over a same-named file one level up."""
        for candidate in (config_dir / ".claude.json", config_dir.parent / ".claude.json"):
            data = self._read_json(candidate)
            if data is None:
                continue
            raw = data.get(_CLAUDE_CACHE_KEY)
            if not isinstance(raw, list):
                return []
            return [m for m in (self._claude_model(e) for e in raw) if m is not None]
        return []

    @staticmethod
    def _claude_model(entry: Any) -> AgentModel | None:
        if not isinstance(entry, dict):
            return None
        value = entry.get("value")
        if not isinstance(value, str) or not value.strip():
            return None
        label = entry.get("label")
        description = entry.get("description")
        return AgentModel(
            id=value,
            label=label if isinstance(label, str) else "",
            description=description if isinstance(description, str) else "",
            source="discovered",
        )

    # --- codex ---------------------------------------------------------------

    def _codex(self, config_dir: pathlib.Path) -> list[AgentModel]:
        """Codex names its model in ``config.toml`` — the top-level default plus
        one per ``[profiles.<name>]``. There are no labels to read, so these
        arrive as bare ids."""
        data = self._read_toml(config_dir / "config.toml")
        if data is None:
            return []
        found: list[AgentModel] = []
        top = data.get("model")
        if isinstance(top, str) and top.strip():
            found.append(AgentModel(id=top, source="discovered"))
        profiles = data.get("profiles")
        if isinstance(profiles, dict):
            for profile in profiles.values():
                if not isinstance(profile, dict):
                    continue
                model = profile.get("model")
                if isinstance(model, str) and model.strip():
                    found.append(AgentModel(id=model, source="discovered"))
        return found

    # --- IO ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: pathlib.Path) -> dict[str, Any] | None:
        try:
            with path.open("rb") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            _log.debug("agent.model_discovery.unreadable path=%s", path, exc_info=True)
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _read_toml(path: pathlib.Path) -> dict[str, Any] | None:
        try:
            with path.open("rb") as fh:
                return tomllib.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            _log.debug("agent.model_discovery.unreadable path=%s", path, exc_info=True)
            return None


__all__ = ["NativeConfigModelDiscovery"]
