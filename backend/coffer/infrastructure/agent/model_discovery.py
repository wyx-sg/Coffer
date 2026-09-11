"""On-disk model discovery + the composite that fans the sources out.

``NativeConfigModelDiscovery`` reads what each CLI has already written down for
itself: Claude Code caches the extra options its own picker offers in
``.claude.json``, and Codex's ``config.toml`` names the model each profile runs.
Those files capture choices the user made locally — a profile pinned to
something unusual, an option the CLI cached after a login — which no amount of
interrogating the binary would reveal, so they stay a source in their own right.

``ChainedModelDiscovery`` is the composite the composition root wires: it asks
every source about the agent and concatenates the answers, so the ORDER of the
sources is the order of the picker.

Best-effort by contract (``ModelDiscoveryPort``): every failure is an empty
list. A missing file is the ordinary case — the user may simply never have
opened that CLI — so it is not even logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import tomllib
from collections.abc import Sequence
from typing import Any

from coffer.application.agent.model_catalogue import ModelDiscoveryPort
from coffer.domain.agent.model_catalogue import AgentModel

_log = logging.getLogger(__name__)

#: Claude Code's cache of the extra model options its own picker offers, e.g.
#: ``[{"value": "…[1m]", "label": "…", "description": "…"}]``.
_CLAUDE_CACHE_KEY = "additionalModelOptionsCache"


class ChainedModelDiscovery:
    """``ModelDiscoveryPort`` that concatenates several sources in order.

    Sources are asked one after another rather than concurrently: the expensive
    ones each apply to a different agent type, so at most one of them actually
    does work on any given call, and sequencing keeps the ordering obvious.
    Dedupe by id is the catalogue service's job — this only decides the order.
    """

    def __init__(self, sources: Sequence[ModelDiscoveryPort]) -> None:
        self._sources = list(sources)

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        models: list[AgentModel] = []
        for source in self._sources:
            try:
                models.extend(await source.discover(agent_key=agent_key, config_dir=config_dir))
            except Exception:
                # One misbehaving source must not cost the user the others.
                _log.debug(
                    "agent.model_discovery.source_failed source=%s",
                    type(source).__name__,
                    exc_info=True,
                )
        return models


class NativeConfigModelDiscovery:
    """``ModelDiscoveryPort`` backed by the agent's native config file."""

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        if config_dir is None:
            # No agent of this type is registered, so there is no config dir to
            # read; the binary-level sources still answer for this agent.
            return []
        if agent_key == "claude_code":
            return await asyncio.to_thread(self._claude_code, config_dir)
        if agent_key == "codex":
            return await asyncio.to_thread(self._codex, config_dir)
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
            found.append(AgentModel(id=top))
        profiles = data.get("profiles")
        if isinstance(profiles, dict):
            for profile in profiles.values():
                if not isinstance(profile, dict):
                    continue
                model = profile.get("model")
                if isinstance(model, str) and model.strip():
                    found.append(AgentModel(id=model))
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


__all__ = ["ChainedModelDiscovery", "NativeConfigModelDiscovery"]
