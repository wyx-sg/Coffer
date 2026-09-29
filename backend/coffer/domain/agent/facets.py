"""Agent mechanism facets — the ports an :class:`AgentDescriptor` names.

ADR agent-mechanisms-are-optional-facets-on-the-descriptor. The descriptor
table (``descriptor.py``) holds per-agent *values*; this module holds the
shape of the per-agent *mechanisms*. Four facets, each optional:

- ``projection`` — a registry of what Coffer can place into the agent, keyed by
  asset type x landing point, each entry carrying its translation and a
  minimal capability declaration (:class:`AgentProjection`);
- ``driver`` — how Coffer runs a turn on the agent;
- ``memory_reader`` — how the agent's native memory is read (read only);
- ``dependency_probe`` — whether the agent's program is installed here and
  which version (:class:`DependencyProbe`).

The pure table in ``descriptor.py`` carries none of them. Implementations live
in the infrastructure layer (and, for the provider translation, in the
provider kind's pure domain), so they are **bound at the composition root**:
each implementation declares the agent type it serves, and :func:`bind_facets`
groups them onto a copy of the table. Consumers receive the resulting
:class:`AgentCatalog` and ask it for a facet; none of them branches on
``AgentType`` (``scripts/check_agent_type_branches.py``).

Where a port belongs to the kind that consumes it (the memory kind's reader
and delivery hook, the chat kind's driver, the provider kind's translation),
the port type is that kind's Protocol, named here under ``TYPE_CHECKING`` only
— annotation-only imports execute nothing and the cross-kind fence does not
count them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from coffer.domain.agent.detection import ProgramInfo
from coffer.domain.agent.mcp_injection import McpInjectionSpec
from coffer.domain.agent.types import AgentType

if TYPE_CHECKING:
    from coffer.application.chat.ports import AgentDriver
    from coffer.domain.agent.descriptor import AgentDescriptor
    from coffer.domain.memory.delivery import DeliveryAdapter
    from coffer.domain.memory.reader import MemoryReader
    from coffer.domain.provider.agent_projection import ProviderProjection


# --- projection registry --------------------------------------------------------


class AssetType(StrEnum):
    """What Coffer can place into an agent. A new asset type is a new member
    plus a registry entry on each agent that can receive it."""

    MCP_SERVER = "mcp_server"
    SKILL = "skill"
    PROVIDER = "provider"
    DELIVERY_HOOK = "delivery_hook"


class Landing(StrEnum):
    """Where an asset lands.

    ``user`` is the agent's own config directory; ``project`` is inside a
    repository; ``shared`` is a directory more than one agent reads, written
    once and kept while any reader still wants it. Every entry the two shipped
    agents have today lands at ``user``.
    """

    USER = "user"
    PROJECT = "project"
    SHARED = "shared"


@dataclass(frozen=True)
class ProjectionEntry:
    """One registry row: an asset type, where it lands, and in which file.

    ``config_key`` names the allowlisted file the asset is written into (the
    security boundary of the config-file allowlist applies); ``subpath`` names
    a directory under the config directory for a directory landing (skills).
    Exactly one of the two is set.
    """

    asset: AssetType
    landing: Landing
    config_key: str | None = None
    subpath: str | None = None


@dataclass(frozen=True)
class AgentProjection:
    """The projection facet: every asset this agent can receive.

    The capability declarations are deliberately small — only what a shipped
    agent uses:

    - MCP: the entry shape (:class:`McpInjectionSpec`);
    - skills: the directory under the config dir;
    - provider: the translation, which also declares the wire protocols the
      agent's native config speaks (possibly none);
    - delivery hook: the hook adapter, which declares its event.

    Provider projection keeps a reserved second mode — pointing the agent at a
    local proxy instead of writing the endpoint — which is a declared option of
    this facet and is not implemented.
    """

    mcp: McpInjectionSpec | None = None
    skill_subpath: str | None = None
    provider: ProviderProjection | None = None
    delivery_hook: DeliveryAdapter | None = None

    @property
    def entries(self) -> tuple[ProjectionEntry, ...]:
        """The registry, in the order a reconciler would visit it."""
        rows: list[ProjectionEntry] = []
        if self.mcp is not None:
            rows.append(ProjectionEntry(AssetType.MCP_SERVER, Landing.USER, self.mcp.config_key))
        if self.skill_subpath is not None:
            rows.append(ProjectionEntry(AssetType.SKILL, Landing.USER, subpath=self.skill_subpath))
        if self.provider is not None:
            rows.append(ProjectionEntry(AssetType.PROVIDER, Landing.USER, self.provider.config_key))
        if self.delivery_hook is not None:
            rows.append(
                ProjectionEntry(
                    AssetType.DELIVERY_HOOK, Landing.USER, self.delivery_hook.config_key
                )
            )
        return tuple(rows)

    def entry(self, asset: AssetType) -> ProjectionEntry | None:
        return next((e for e in self.entries if e.asset is asset), None)

    def accepts(self, asset: AssetType) -> bool:
        return self.entry(asset) is not None


# --- dependency probe -----------------------------------------------------------


class DependencyProbe(Protocol):
    """Whether the agent's program is installed here, and which version.

    Finds the program on the agent's real ``PATH`` and asks it for its version
    with a bounded timeout. Never runs anything that needs a login. Cheap to
    call repeatedly: an implementation caches by the binary it found.
    """

    @property
    def program(self) -> str:
        """The executable the probe looks for (``claude``, ``codex``)."""
        ...

    def probe(self) -> ProgramInfo: ...


# --- the catalogue --------------------------------------------------------------


class AgentCatalog:
    """The descriptor table with its facets bound. Built once at the
    composition root and handed to every consumer of a mechanism."""

    def __init__(self, descriptors: dict[AgentType, AgentDescriptor]) -> None:
        self._descriptors = dict(descriptors)

    def __iter__(self) -> Iterator[AgentDescriptor]:
        return iter(self._descriptors[t] for t in AgentType if t in self._descriptors)

    def get(self, agent_type: AgentType) -> AgentDescriptor:
        return self._descriptors[agent_type]

    def projection(self, agent_type: AgentType) -> AgentProjection | None:
        d = self._descriptors.get(agent_type)
        return d.projection if d is not None else None

    def provider_projection(self, agent_type: AgentType) -> ProviderProjection | None:
        p = self.projection(agent_type)
        return p.provider if p is not None else None

    def delivery_hook(self, agent_type: AgentType) -> DeliveryAdapter | None:
        p = self.projection(agent_type)
        return p.delivery_hook if p is not None else None

    def driver(self, agent_type: AgentType) -> AgentDriver[Any] | None:
        d = self._descriptors.get(agent_type)
        return d.driver if d is not None else None

    def memory_reader(self, agent_type: AgentType) -> MemoryReader | None:
        d = self._descriptors.get(agent_type)
        return d.memory_reader if d is not None else None

    def memory_readers(self) -> dict[str, MemoryReader]:
        """Every bound memory reader, keyed by the agent type's value — the
        shape the memory kind's aggregation pass looks readers up in."""
        return {d.type.value: d.memory_reader for d in self if d.memory_reader is not None}

    def drivers(self) -> tuple[AgentDriver[Any], ...]:
        """Every bound driver, in agent-type order."""
        return tuple(d.driver for d in self if d.driver is not None)

    def dependency_probe(self, agent_type: AgentType) -> DependencyProbe | None:
        d = self._descriptors.get(agent_type)
        return d.dependency_probe if d is not None else None

    def agents_speaking(self, protocol: str) -> tuple[AgentType, ...]:
        """The agent types whose provider projection declares ``protocol``, in
        ``AgentType`` order. Any number, including none."""
        return tuple(
            d.type
            for d in self
            if d.projection is not None
            and d.projection.provider is not None
            and protocol in d.projection.provider.protocols
        )


def _by_type[T](items: Iterable[T], declared: Callable[[T], str], facet: str) -> dict[AgentType, T]:
    """Group implementations by the agent each one declares. The declaration
    is the agent type's value, so a kind that may not import this one (the
    chat kind's drivers) declares it as a plain string."""
    out: dict[AgentType, T] = {}
    for item in items:
        agent_type = AgentType(declared(item))
        if agent_type in out:
            raise ValueError(f"two {facet} implementations declare {agent_type.value!r}")
        out[agent_type] = item
    return out


def bind_facets(
    descriptors: dict[AgentType, AgentDescriptor],
    *,
    providers: Iterable[ProviderProjection] = (),
    delivery_hooks: Iterable[DeliveryAdapter] = (),
    drivers: Iterable[AgentDriver[Any]] = (),
    memory_readers: Iterable[MemoryReader] = (),
    probe_for: Callable[[AgentDescriptor], DependencyProbe | None] | None = None,
) -> AgentCatalog:
    """Bind each implementation to the record of the agent it declares.

    Grouping is by the agent each implementation declares, so the caller
    lists implementations and never says which agent is which. The MCP and
    skill entries come from the record's values; an agent with nothing to
    receive gets no projection facet at all. ``probe_for`` builds the
    dependency probe from the record (the probe is generic: it only needs the
    record's program name).
    """
    provider_by = _by_type(providers, lambda p: p.agent_type, "provider projection")
    hook_by = _by_type(delivery_hooks, lambda h: h.agent_type, "delivery hook")
    driver_by = _by_type(drivers, lambda d: d.agent_key, "driver")
    reader_by = _by_type(memory_readers, lambda r: r.agent_type, "memory reader")
    bound: dict[AgentType, AgentDescriptor] = {}
    for agent_type, d in descriptors.items():
        projection = AgentProjection(
            mcp=d.mcp,
            skill_subpath=d.skill_subpath,
            provider=provider_by.get(agent_type),
            delivery_hook=hook_by.get(agent_type),
        )
        bound[agent_type] = dataclasses.replace(
            d,
            projection=projection if projection.entries else None,
            driver=driver_by.get(agent_type),
            memory_reader=reader_by.get(agent_type),
            dependency_probe=probe_for(d) if probe_for is not None else None,
        )
    return AgentCatalog(bound)


__all__ = [
    "AgentCatalog",
    "AgentProjection",
    "AssetType",
    "DependencyProbe",
    "Landing",
    "ProjectionEntry",
    "bind_facets",
]
