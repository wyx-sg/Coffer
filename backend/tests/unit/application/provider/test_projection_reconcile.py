"""The provider projection target's direction policy, over in-memory fakes.

Ported from the boot heal it replaced. The motivating machine: an
``is_active`` connection routed to Claude Code, and ``settings.json`` carrying
no Coffer keys at all — the agent had been on its built-in login the whole
time, while every surface answered from the flag. What these pin down is the
DIRECTION: on a pass with no warrant Coffer corrects its own record and never
rewrites the agent's config, because a leftover flag is no warrant to re-route
somebody's agent.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.provider.projection_reconcile import TARGET, ProviderProjectionTarget
from coffer.application.provider.projector import ProviderProjector
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import CodexProviderProjection
from coffer.domain.provider.api_key_helper import proxy_token_args, proxy_token_helper
from coffer.domain.provider.codex_projection import CodexAuthCommand
from coffer.domain.provider.projection import (
    apply_anthropic_settings,
    apply_codex_provider,
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
_AUTH = CodexAuthCommand(_CLI, proxy_token_args(_AGENT_UID))


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
        id=1,
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


def _agent(config_dir: pathlib.Path, *, enabled: bool = True) -> Resource:
    return _resource(
        "agent",
        "claude-code",
        {"type": "claude_code", "config_dir": str(config_dir)},
        uid=_AGENT_UID,
        enabled=enabled,
    )


def _connection(*, is_active: bool = True) -> Resource:
    return _resource(
        "provider",
        "agnes",
        {
            "protocol": "openai",
            "base_url": _BASE_URL,
            "secret_ref": "agnes-key",
            "is_active": is_active,
        },
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
        loopback_proxy=True,
    )


async def _run(
    store: _Store,
    agents: list[Resource],
    providers: list[Resource],
    *,
    trigger: Trigger = Trigger.BOOT,
    fail_deactivate: bool = False,
) -> tuple[list[ItemResult], list[AgentType]]:
    calls: list[AgentType] = []

    async def deactivate(agent_type: AgentType) -> object:
        if fail_deactivate:
            raise RuntimeError("registry is busy")
        calls.append(agent_type)
        return None

    reconciler = Reconciler(audit=_Audit())  # type: ignore[arg-type]
    reconciler.register(
        ProviderProjectionTarget(
            providers=_Lister(providers),
            agents=_Lister(agents),
            projector=ProviderProjector(store, agents=agent_catalog(), cli_resolver=lambda: _CLI),
            store=store,
            deactivate=deactivate,
        )
    )
    report = await reconciler.run(trigger=trigger)
    assert report.failures == ()
    return [r for r in report.results if r.change.difference.target == TARGET], calls


async def test_a_flag_the_agent_config_denies_is_cleared(tmp_path: pathlib.Path) -> None:
    # settings.json exists and is perfectly valid — it simply has none of
    # Coffer's keys in it, which is exactly what was found in the wild.
    store = _Store({_settings(tmp_path): json.dumps({"env": {}, "theme": "dark"})})
    results, calls = await _run(store, [_agent(tmp_path)], [_connection()])

    assert calls == [AgentType.CLAUDE_CODE], "the agent type must be put back on its built-in login"
    assert [r.change.decision.reason_code for r in results] == ["flag_contradicted"]
    assert "built-in login" in results[0].change.decision.reason
    assert store.writes == 0, "the agent's config is never written on a stale flag"


async def test_a_flag_the_agent_config_confirms_is_left_alone(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): _projected_settings()})
    results, calls = await _run(store, [_agent(tmp_path)], [_connection()])

    assert results == []
    assert calls == []


@pytest.mark.parametrize(
    "helper",
    [
        # What Coffer wrote before the CLI was named by absolute path: still
        # Coffer's, so a file carrying only this is still a live projection.
        f"coffer provider key --connection-uid {_CONNECTION_UID}",
        # The key-helper form before the proxy, with a path a shell needs quoted.
        f"'/Users/me/My Apps/coffer' provider key --connection-uid {_CONNECTION_UID}",
    ],
    ids=["bare", "quoted-absolute"],
)
async def test_either_helper_form_counts_as_projected(tmp_path: pathlib.Path, helper: str) -> None:
    """Present, so the flag stands — but not the command Coffer writes now,
    so it is repaired as stale rather than passing a presence test."""
    store = _Store({_settings(tmp_path): _projected_settings(helper)})
    results, calls = await _run(store, [_agent(tmp_path)], [_connection()])

    assert calls == []
    assert [r.change.decision.reason_code for r in results] == ["projection_stale"]
    assert results[0].change.difference.changed_params == ("apiKeyHelper",)
    assert results[0].outcome is Outcome.APPLIED
    doc = json.loads(store.files[_settings(tmp_path)])
    assert doc["apiKeyHelper"] == proxy_token_helper(_AGENT_UID, coffer_cli=_CLI)


async def test_an_inactive_connection_is_not_touched(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): "{}"})
    results, calls = await _run(store, [_agent(tmp_path)], [_connection(is_active=False)])

    assert results == []
    assert calls == []


async def test_no_registered_agent_of_that_type_means_another_machine(
    tmp_path: pathlib.Path,
) -> None:
    """The flag rides the synced row. With no Claude Code registered here it
    describes some other machine's agents, and clearing it would undo a switch
    the user made there."""
    results, calls = await _run(_Store(), [], [_connection()])

    assert results == []
    assert calls == []


async def test_a_disabled_agent_is_not_judged(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): "{}"})
    results, calls = await _run(store, [_agent(tmp_path, enabled=False)], [_connection()])

    assert results == []
    assert calls == []


async def test_an_unreadable_config_is_never_guessed_absent(tmp_path: pathlib.Path) -> None:
    """Guessing "absent" from a file we could not read would clear a flag on no
    evidence — the worse of the two mistakes."""
    results, calls = await _run(_UnreadableStore(), [_agent(tmp_path)], [_connection()])

    assert results == []
    assert calls == []


async def test_a_failing_deactivate_fails_the_item_not_the_pass(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): "{}"})
    results, _ = await _run(store, [_agent(tmp_path)], [_connection()], fail_deactivate=True)

    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "registry is busy" in (results[0].error or "")


async def test_keys_without_an_active_connection_are_reported(tmp_path: pathlib.Path) -> None:
    store = _Store({_settings(tmp_path): _projected_settings()})
    results, calls = await _run(
        store, [_agent(tmp_path)], [_connection(is_active=False)], trigger=Trigger.PERIOD
    )

    assert [r.change.decision.reason_code for r in results] == ["projection_unclaimed"]
    assert results[0].outcome is Outcome.PLANNED
    assert store.writes == 0 and calls == []


async def test_an_import_removes_keys_no_active_connection_claims(tmp_path: pathlib.Path) -> None:
    """A switch made on another machine reaches this one's agents: after an
    import a type with no active connection is de-projected (spec
    provider-switching "Converge connections across machines")."""
    store = _Store({_settings(tmp_path): _projected_settings()})
    results, _ = await _run(
        store, [_agent(tmp_path)], [_connection(is_active=False)], trigger=Trigger.IMPORT
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


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a leftover shell exclude entry is not a Codex projection"
)
def test_a_leftover_codex_shell_exclude_is_not_a_projection() -> None:
    """The ``shell_environment_policy.exclude`` entry only hides the key; with the
    provider block removed by hand it selects nothing, so the flag is stale."""
    projected = apply_codex_provider(
        "", base_url=_BASE_URL, model="m", wire_api="responses", display_name="x", auth=_AUTH
    )
    facet = CodexProviderProjection()
    assert facet.is_present(projected)
    leftover = '[shell_environment_policy]\nexclude = ["COFFER_PROVIDER_KEY"]\n'
    assert not facet.is_present(leftover)
