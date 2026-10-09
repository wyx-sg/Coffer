"""The agents a memory sync reads, and a source it could not read.

Built by the composition root from the registered agent resources, so this
package never reaches into the agent kind's own service.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSource:
    """A registered agent, reduced to what the sync needs: its resource name,
    which reader and writer apply to it, and its config directory."""

    agent: str
    agent_type: str
    config_dir: str


@dataclass(frozen=True)
class SourceFailure:
    """One reader's ``UnreadableMemory`` for one source, isolated."""

    agent: str
    path: str
    reason: str
