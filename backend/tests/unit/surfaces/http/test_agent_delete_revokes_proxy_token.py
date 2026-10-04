"""Deleting an agent deletes its local proxy token with it (spec provider-switching
"Authenticate each agent to the proxy with its own local token")."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.provider.proxy_tokens import ProxyTokenService, token_ref
from coffer.surfaces.http.provider_wiring import _revoke_token_on_agent_delete


class _Secrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.values.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.values[ref] = value

    def delete(self, ref: str) -> None:
        self.values.pop(ref, None)

    def list_refs(self) -> list[tuple[str, str, str]]:
        return [(ref, "", "") for ref in sorted(self.values)]


@dataclasses.dataclass(frozen=True)
class _Kind:
    on_delete: Any = None


def _app(kind: _Kind) -> Any:
    return SimpleNamespace(state=SimpleNamespace(kinds={"agent": kind}))


@pytest.mark.asyncio
async def test_deleting_an_agent_revokes_its_token_and_only_its_token() -> None:
    secrets = _Secrets()
    tokens = ProxyTokenService(secrets)
    await tokens.token_for("agent-a")
    await tokens.token_for("agent-b")
    app = _app(_Kind())
    _revoke_token_on_agent_delete(app, SimpleNamespace(tokens=tokens))  # type: ignore[arg-type]

    await app.state.kinds["agent"].on_delete(SimpleNamespace(uid="u-a", name="agent-a"))

    assert secrets.get(token_ref("agent-a")) is None
    assert secrets.get(token_ref("agent-b")) is not None


@pytest.mark.asyncio
async def test_the_kinds_own_delete_hook_still_runs_first() -> None:
    secrets = _Secrets()
    tokens = ProxyTokenService(secrets)
    await tokens.token_for("agent-a")
    seen: list[str] = []

    async def previous(agent: Any) -> None:
        seen.append(agent.name)
        assert secrets.get(token_ref("agent-a")) is not None  # revoked after, not before

    app = _app(_Kind(on_delete=previous))
    _revoke_token_on_agent_delete(app, SimpleNamespace(tokens=tokens))  # type: ignore[arg-type]

    await app.state.kinds["agent"].on_delete(SimpleNamespace(uid="u-a", name="agent-a"))

    assert seen == ["agent-a"]
    assert secrets.get(token_ref("agent-a")) is None


@pytest.mark.asyncio
async def test_prune_deletes_tokens_no_current_agent_goes_by() -> None:
    """A token stored under a key no agent goes by — a removed agent's, or an
    old uid-keyed one — is deleted; current agents' tokens and other secrets stay."""
    secrets = _Secrets()
    tokens = ProxyTokenService(secrets)
    await tokens.token_for("codex")
    secrets.set("proxy-token/9a006a32d0bf5787955c43d54e4b44e9", "cfr_old")
    secrets.set("secret/github", "ghp_x")

    assert await tokens.prune(["codex"]) == ["proxy-token/9a006a32d0bf5787955c43d54e4b44e9"]

    assert sorted(secrets.values) == ["proxy-token/codex", "secret/github"]
