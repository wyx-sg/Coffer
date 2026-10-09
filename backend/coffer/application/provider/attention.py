"""What about the model provider connections needs a person (the Overview list).

Read from each connection's kept health verdict (``application/provider/health``),
and asked only of the connections something runs on — an agent whose record
names the connection and that the connection still reaches, or Coffer's own
speech to text. A connection nothing uses may be down on purpose (a local
runtime that is not started); the provider list still marks it red.

- ``provider_key_rejected`` — the endpoint refuses the stored key (401/403, from
  a check or an agent's real request). Fixed by a new key, on the connection's
  page;
- ``provider_unreachable`` — the endpoint does not answer. The action checks it
  again in place.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.provider.targets import connection_for_agent
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.health import HealthStatus, ProviderHealth
from coffer.domain.resource import Resource

KIND = "provider"


class ResourcesPort(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> Sequence[Resource]: ...


class HealthPort(Protocol):
    async def all(self) -> dict[str, ProviderHealth]: ...


def _in_use(connections: Sequence[Resource], agents: Sequence[Resource]) -> set[str]:
    used = {connection.uid for agent in agents if (connection := _on(agent, connections))}
    for connection in connections:
        try:
            if ProviderConfig.model_validate(connection.config).transcribe_default:
                used.add(connection.uid)
        except ValueError:
            continue
    return used


def _on(agent: Resource, connections: Sequence[Resource]) -> Resource | None:
    found = connection_for_agent(agent, connections)
    return found[0] if found is not None else None


class ProviderAttentionSource:
    name = "provider"
    feature: str | None = None

    def __init__(self, *, resources: ResourcesPort, health: HealthPort) -> None:
        self._resources = resources
        self._health = health

    async def items(self) -> Sequence[AttentionItem]:
        connections = await self._resources.list(kind=KIND, enabled=True)
        if not connections:
            return []
        verdicts = await self._health.all()
        if not any(v.failing for v in verdicts.values()):
            return []
        used = _in_use(connections, await self._resources.list(kind="agent"))
        out: list[AttentionItem] = []
        for connection in connections:
            verdict = verdicts.get(connection.uid)
            if verdict is None or not verdict.failing or connection.uid not in used:
                continue
            out.append(_item(connection, verdict))
        return out


def _item(connection: Resource, verdict: ProviderHealth) -> AttentionItem:
    title = connection.title or connection.name
    if verdict.status is HealthStatus.KEY_REJECTED:
        return AttentionItem(
            kind=KIND,
            uid=connection.uid,
            title=title,
            reason_code="provider_key_rejected",
            reason="The endpoint refuses its API key, so the agents on it get no answer.",
            severity=Severity.ERROR,
            # The key is replaced on the connection's page; the action names
            # the connection itself.
            action=AttentionAction(
                verb="replace_key", method="GET", path=f"/api/v1/providers/{connection.uid}"
            ),
            since=verdict.started,
        )
    reason = "Its endpoint does not answer"
    reason += f": {verdict.message}" if verdict.message else "."
    return AttentionItem(
        kind=KIND,
        uid=connection.uid,
        title=title,
        reason_code="provider_unreachable",
        reason=reason,
        severity=Severity.ERROR,
        action=AttentionAction(
            verb="check", method="POST", path=f"/api/v1/providers/{connection.uid}/check"
        ),
        since=verdict.started,
    )


__all__ = ["ProviderAttentionSource"]
