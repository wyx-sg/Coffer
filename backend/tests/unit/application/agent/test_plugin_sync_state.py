"""The agent plugin inventory as a synced state area (spec vault-export-import).

It is an INVENTORY, not a replicator: export writes down what this machine has,
import stores it and touches no agent config. These tests pin that asymmetry,
because "sync it" and "install it" look alike until someone writes into another
tool's private config format.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from coffer.application.agent.plugin_sync_state import AREA, AgentPluginSyncState


@dataclass
class _Plugin:
    id: str
    name: str
    marketplace: str
    enabled: bool
    version: str | None = None


@dataclass
class _Market:
    name: str
    source_type: str | None = None
    source: str | None = None


@dataclass
class _Listing:
    items: list[_Plugin]
    marketplaces: list[_Market]


@dataclass
class _Resource:
    name: str


class _Resources:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    async def list(self, kind: str | None = None) -> list[_Resource]:
        assert kind == "agent"
        return [_Resource(n) for n in self._names]


class _Plugins:
    def __init__(self, by_agent: dict[str, _Listing | Exception]) -> None:
        self._by_agent = by_agent
        self.calls: list[str] = []

    async def list_plugins(self, name: str):
        self.calls.append(name)
        result = self._by_agent[name]
        if isinstance(result, Exception):
            raise result
        return result


def _state(by_agent):
    return AgentPluginSyncState(_Resources(list(by_agent)), _Plugins(by_agent))


@pytest.mark.asyncio
async def test_area_is_the_fifth_state_area() -> None:
    assert AREA == "agent-plugins"


@pytest.mark.asyncio
async def test_export_writes_one_doc_per_agent_with_plugins() -> None:
    state = _state(
        {
            "codex": _Listing(
                items=[
                    _Plugin("lint@npm", "lint", "npm", True, "1.2.0"),
                    _Plugin("fmt@npm", "fmt", "npm", False),
                ],
                marketplaces=[_Market("npm", "git", "https://example/npm")],
            )
        }
    )
    docs, owned = await state.export_docs()

    assert owned == ["codex"]
    [(path, doc)] = docs
    assert path == "codex"
    assert doc["agent"] == "codex"
    # Sorted, so two machines that hold the same plugins produce the same bytes.
    assert [p["id"] for p in doc["plugins"]] == ["fmt@npm", "lint@npm"]
    assert doc["plugins"][1]["version"] == "1.2.0"
    assert doc["plugins"][0]["version"] is None
    assert doc["marketplaces"] == [
        {"name": "npm", "source_type": "git", "source": "https://example/npm"}
    ]


@pytest.mark.asyncio
async def test_an_agent_with_no_plugins_writes_no_doc() -> None:
    state = _state({"claude_code": _Listing(items=[], marketplaces=[])})
    docs, owned = await state.export_docs()
    assert docs == []
    # Still owned — the agent exists, it just has nothing to carry.
    assert owned == ["claude_code"]


@pytest.mark.asyncio
async def test_one_unreadable_agent_does_not_lose_the_others() -> None:
    """A bundle with fifteen of sixteen agents beats no bundle."""
    state = _state(
        {
            "broken": OSError("config dir vanished"),
            "codex": _Listing(items=[_Plugin("a@m", "a", "m", True)], marketplaces=[]),
        }
    )
    docs, owned = await state.export_docs()
    assert [p for p, _ in docs] == ["codex"]
    assert owned == ["broken", "codex"]


@pytest.mark.asyncio
async def test_import_writes_nothing_and_reports_nothing() -> None:
    """The whole point. Coffer has no plugin install path and deliberately does
    not hand-write another tool's private config; the list lands in the vault
    for the user to act on."""
    plugins = _Plugins({})
    state = AgentPluginSyncState(_Resources([]), plugins)
    errors = await state.import_docs([("codex", {"agent": "codex", "plugins": [{"id": "a@m"}]})])
    assert errors == []
    assert plugins.calls == []
