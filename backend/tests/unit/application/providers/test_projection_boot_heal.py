"""Boot heal for an ``is_active`` flag the agent's own config contradicts.

The motivating machine: an ``is_active`` connection routed to Claude Code, and
``~/.claude/settings.json`` carrying no Coffer keys at all — the agent had been
on its built-in login the whole time, while every surface answered from the
flag. What these pin down is not just that it heals, but the DIRECTION: Coffer
corrects its own record and never rewrites the agent's config, because a
leftover flag is no warrant to re-route somebody's agent.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Any

from coffer.application.provider.boot_reconcile import ProviderProjectionBootHeal
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.projection import anthropic_api_key_helper, apply_anthropic_settings
from coffer.domain.resource import Resource

_NOW = datetime(2026, 9, 10, tzinfo=UTC)
_BASE_URL = "https://gateway.example/v1"


def _resource(kind: str, name: str, config: dict[str, Any], *, enabled: bool = True) -> Resource:
    return Resource(
        id=1,
        kind=kind,
        name=name,
        description=None,
        config=config,
        enabled=enabled,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _agent(config_dir: pathlib.Path, *, enabled: bool = True) -> Resource:
    return _resource(
        "agent",
        "claude-code",
        {"type": "claude_code", "config_dir": str(config_dir)},
        enabled=enabled,
    )


def _connection(*, is_active: bool = True) -> Resource:
    return _resource(
        "provider",
        "agnes",
        {
            "protocol": "openai",
            "base_url": _BASE_URL,
            "credential_ref": "agnes-key",
            # The shape that surfaced this: an openai endpoint routed to Claude Code.
            "compatible_agents": ["claude_code"],
            "is_active": is_active,
        },
    )


class _Lister:
    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self) -> list[Resource]:
        return list(self._rows)


class _Store:
    def __init__(self, files: dict[pathlib.Path, str] | None = None) -> None:
        self.files = dict(files or {})

    def read_text(self, path: pathlib.Path) -> str | None:
        return self.files.get(path)


class _UnreadableStore:
    def read_text(self, path: pathlib.Path) -> str | None:
        raise PermissionError(path)


def _settings_path(config_dir: pathlib.Path) -> pathlib.Path:
    return config_dir / "settings.json"


def _projected_settings() -> str:
    return apply_anthropic_settings(
        "",
        base_url=_BASE_URL,
        model=None,
        fast_model=None,
        api_key_helper=anthropic_api_key_helper("agnes"),
    )


def _heal(store: Any, agents: list[Resource], providers: list[Resource]):
    calls: list[Protocol] = []

    async def deactivate(wire: Protocol) -> object:
        calls.append(wire)
        return None

    heal = ProviderProjectionBootHeal(
        providers=_Lister(providers),
        agents=_Lister(agents),
        config_store=store,
        deactivate=deactivate,
    )
    return heal, calls


async def test_a_flag_the_agent_config_denies_is_cleared(tmp_path: pathlib.Path) -> None:
    # settings.json exists and is perfectly valid — it simply has none of
    # Coffer's keys in it, which is exactly what was found in the wild.
    store = _Store({_settings_path(tmp_path): json.dumps({"env": {}, "theme": "dark"})})
    heal, calls = _heal(store, [_agent(tmp_path)], [_connection()])

    notes = await heal.heal()

    assert calls == [Protocol.ANTHROPIC], "the agent type must be put back on its built-in login"
    assert any("agnes" in n and "built-in login" in n for n in notes)


async def test_a_flag_the_agent_config_confirms_is_left_alone(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings_path(tmp_path): _projected_settings()})
    heal, calls = _heal(store, [_agent(tmp_path)], [_connection()])

    assert await heal.heal() == []
    assert calls == []


async def test_an_inactive_connection_is_not_touched(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings_path(tmp_path): "{}"})
    heal, calls = _heal(store, [_agent(tmp_path)], [_connection(is_active=False)])

    assert await heal.heal() == []
    assert calls == []


async def test_no_registered_agent_of_that_type_means_another_machine(
    tmp_path: pathlib.Path,
) -> None:
    """The flag rides the synced row. With no Claude Code registered here it
    describes some other machine's agents, and clearing it would undo a switch
    the user made there."""
    heal, calls = _heal(_Store(), [], [_connection()])

    assert await heal.heal() == []
    assert calls == []


async def test_an_unreadable_config_is_assumed_projected(tmp_path: pathlib.Path) -> None:
    """Guessing "absent" from a file we could not read would clear a flag on no
    evidence — the worse of the two mistakes."""
    heal, calls = _heal(_UnreadableStore(), [_agent(tmp_path)], [_connection()])

    assert await heal.heal() == []
    assert calls == []


async def test_a_failing_deactivate_is_reported_not_raised(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings_path(tmp_path): "{}"})

    async def deactivate(wire: Protocol) -> object:
        raise RuntimeError("registry is busy")

    heal = ProviderProjectionBootHeal(
        providers=_Lister([_connection()]),
        agents=_Lister([_agent(tmp_path)]),
        config_store=store,
        deactivate=deactivate,
    )

    notes = await heal.heal()

    assert any("could not clear stale 'agnes'" in n for n in notes)
