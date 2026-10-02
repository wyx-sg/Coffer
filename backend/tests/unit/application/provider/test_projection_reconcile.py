"""The provider projection target's direction policy, over in-memory fakes.

Ported from the boot heal it replaced. The motivating machine: an agent whose
record names a connection, and ``settings.json`` carrying no Coffer keys at all
— the agent had been on its built-in login the whole time, while every surface
answered from the record. What these pin down is the DIRECTION and its reach:
on a pass with no warrant Coffer corrects its own record — that one agent's,
no other — and never rewrites the agent's config, because a leftover choice is
no warrant to re-route somebody's agent. The cases over real files and a real
database are in ``tests/integration/providers/test_projection_reconcile.py``.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Any

from coffer.application.provider.projection_reconcile import TARGET, ProviderProjectionTarget
from coffer.application.provider.projector import ProviderProjector
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.provider.api_key_helper import proxy_token_helper
from coffer.domain.provider.projection import (
    apply_anthropic_settings,
)
from coffer.domain.reconcile import ItemResult, Outcome, Trigger
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from tests.support.facets import agent_catalog

_NOW = datetime(2026, 9, 10, tzinfo=UTC)
_BASE_URL = "https://gateway.example/v1"
_AGENT_UID = "8f1c2d3e4a5b6c7d8e9f0a1b2c3d4e5f"
_CONNECTION_UID = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"
_CLI = "/Users/me/.coffer/bin/coffer"
#: Where the proxy-form projection points Claude Code (the default port).
_PROXY_URL = "http://127.0.0.1:8001/anthropic"


def _resource(
    kind: str,
    name: str,
    config: dict[str, Any],
    *,
    uid: str,
    enabled: bool = True,
    scope: Scope | None = None,
) -> Resource:
    return Resource(
        uid=uid,
        kind=kind,
        name=name,
        description=None,
        config=config,
        enabled=enabled,
        created_at=_NOW,
        updated_at=_NOW,
        scope=scope,
    )


def _agent(
    config_dir: pathlib.Path,
    *,
    enabled: bool = True,
    connection_uid: str | None = _CONNECTION_UID,
) -> Resource:
    return _resource(
        "agent",
        "claude-code",
        {
            "type": "claude_code",
            "config_dir": str(config_dir),
            "connection_uid": connection_uid,
        },
        uid=_AGENT_UID,
        enabled=enabled,
    )


def _connection() -> Resource:
    return _resource(
        "provider",
        "agnes",
        {"protocol": "openai", "base_url": _BASE_URL, "secret_ref": "agnes-key"},
        uid=_CONNECTION_UID,
        # The shape that surfaced this: an openai endpoint routed to Claude
        # Code by its per-agent scope, which names the agent by uid.
        scope=Scope(agents=[_AGENT_UID]),
    )


class _Lister:
    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self) -> list[Resource]:
        return list(self._rows)


class _Store:
    def __init__(self, files: dict[pathlib.Path, str] | None = None) -> None:
        self.files = dict(files or {})
        self.writes = 0

    def read_text(self, path: pathlib.Path) -> str | None:
        return self.files.get(path)

    def write_text_atomic(
        self, path: pathlib.Path, text: str, *, expected_fingerprint: str | None = None
    ) -> None:
        self.writes += 1
        self.files[path] = text

    def fingerprint(self, text: str | None) -> str:
        return str(hash(text))

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        self.writes += 1
        return self.files.pop(path, None) is not None


class _UnreadableStore(_Store):
    def read_text(self, path: pathlib.Path) -> str | None:
        raise PermissionError(path)


class _Audit:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str]] = []

    async def record(self, event_type: str, *, actor: str, **_: Any) -> None:
        self.rows.append((event_type, actor))


def _settings(config_dir: pathlib.Path) -> pathlib.Path:
    return config_dir / "settings.json"


def _projected_settings(helper: str | None = None) -> str:
    """What the proxy-form projection writes: the local proxy's Anthropic
    route and the agent's own token helper, never the upstream or its key."""
    return apply_anthropic_settings(
        "",
        base_url=_PROXY_URL,
        model=None,
        api_key_helper=helper or proxy_token_helper(_AGENT_UID, coffer_cli=_CLI),
    )


async def _run(
    store: _Store,
    agents: list[Resource],
    providers: list[Resource],
    *,
    trigger: Trigger = Trigger.BOOT,
    fail_clear: bool = False,
) -> tuple[list[ItemResult], list[str]]:
    calls: list[str] = []

    async def clear_choice(agent_uid: str) -> object:
        if fail_clear:
            raise RuntimeError("registry is busy")
        calls.append(agent_uid)
        return None

    reconciler = Reconciler(audit=_Audit())  # type: ignore[arg-type]
    reconciler.register(
        ProviderProjectionTarget(
            providers=_Lister(providers),
            agents=_Lister(agents),
            projector=ProviderProjector(store, agents=agent_catalog(), cli_resolver=lambda: _CLI),
            store=store,
            clear_choice=clear_choice,
        )
    )
    report = await reconciler.run(trigger=trigger)
    assert report.failures == ()
    return [r for r in report.results if r.change.difference.target == TARGET], calls


async def test_a_contradicted_choice_clears_only_that_agents_record(
    tmp_path: pathlib.Path,
) -> None:
    """The choice is one field of one agent: Claude Code's file lost Coffer's
    keys, so ITS record is cleared; a Codex agent beside it is judged on its own
    (here it runs on no connection and its file carries keys, which is only
    reported), and no file is written to clear a choice."""
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    codex = _resource(
        "agent",
        "codex",
        {"type": "codex", "config_dir": str(codex_dir), "connection_uid": None},
        uid="c" * 32,
    )
    connection = _resource(
        "provider",
        "agnes",
        {"protocol": "openai", "base_url": _BASE_URL, "secret_ref": "k"},
        uid=_CONNECTION_UID,
    )
    store = _Store(
        {
            _settings(tmp_path): json.dumps({"theme": "dark"}),
            codex_dir / "config.toml": '[model_providers.coffer]\nname = "x"\n',
        }
    )
    results, calls = await _run(
        store, [_agent(tmp_path), codex], [connection], trigger=Trigger.PERIOD
    )

    assert calls == [_AGENT_UID]
    assert "choice_contradicted" in [r.change.decision.reason_code for r in results]
    assert "built-in login" in results[0].change.decision.reason
    assert json.loads(store.files[_settings(tmp_path)]) == {"theme": "dark"}
    assert store.writes == 0, "no agent's file is written to clear a choice"


async def test_a_flag_the_agent_config_confirms_is_left_alone(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): _projected_settings()})
    results, calls = await _run(store, [_agent(tmp_path)], [_connection()])

    assert results == []
    assert calls == []


async def test_an_agent_on_no_connection_is_not_touched(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): "{}"})
    results, calls = await _run(store, [_agent(tmp_path, connection_uid=None)], [_connection()])

    assert results == []
    assert calls == []


async def test_a_connection_no_registered_agent_runs_on_judges_nothing() -> None:
    results, calls = await _run(_Store(), [], [_connection()])

    assert results == []
    assert calls == []


async def test_a_disabled_agent_is_not_judged(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): "{}"})
    results, calls = await _run(store, [_agent(tmp_path, enabled=False)], [_connection()])

    assert results == []
    assert calls == []


async def test_an_unreadable_config_is_never_guessed_absent(tmp_path: pathlib.Path) -> None:
    """Guessing "absent" from a file we could not read would clear a choice on no
    evidence — the worse of the two mistakes."""
    results, calls = await _run(_UnreadableStore(), [_agent(tmp_path)], [_connection()])

    assert results == []
    assert calls == []


async def test_a_failing_clear_fails_the_item_not_the_pass(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): "{}"})
    results, _ = await _run(store, [_agent(tmp_path)], [_connection()], fail_clear=True)

    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "registry is busy" in (results[0].error or "")


async def test_an_import_removes_keys_no_connection_claims(tmp_path: pathlib.Path) -> None:
    """After a sync round's import an agent that runs on no connection is
    de-projected (spec provider-switching "Converge connections across
    machines")."""
    store = _Store({_settings(tmp_path): _projected_settings()})
    results, _ = await _run(
        store, [_agent(tmp_path, connection_uid=None)], [_connection()], trigger=Trigger.IMPORT
    )

    assert [r.outcome for r in results] == [Outcome.APPLIED]
    assert "apiKeyHelper" not in json.loads(store.files[_settings(tmp_path)])


def test_secret_named_values_never_reach_the_rendering() -> None:
    from coffer.domain.provider.projection_params import params_of, render

    params = params_of(
        {"env.ANTHROPIC_API_KEY": "sk-live", "apiKeyHelper": "coffer x"},
        ["env.ANTHROPIC_API_KEY", "apiKeyHelper"],
    )
    assert params["env.ANTHROPIC_API_KEY"] != "sk-live"
    text = render(params)
    assert "sk-live" not in text and "<redacted>" in text and "coffer x" in text
