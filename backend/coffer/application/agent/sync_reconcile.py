"""Agent import gate for sync (spec vault-sync import reconciliation).

Gate: an agent doc only imports where its config dir exists and its skill
dir is usable — the same checks ``AgentService.register`` runs on the front
door. An installation without the agent refuses the doc as not applicable here
(``AGENT_CONFIG_DIR_MISSING``: held, not retried), instead of creating a
registry row pointing at a dead directory; an unusable skill dir is retried.

What an import changes on disk — which skills each agent holds — is not this
module's: the reconciler's import pass (``Trigger.IMPORT``) runs the
``skill_link`` target over the converged rows and this machine's own reach.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from coffer.application.agent.service import ensure_skill_dir
from coffer.application.platform_port import PlatformPort
from coffer.domain.agent.config import AgentConfig
from coffer.domain.errors import AgentConfigDirMissing, ConfigValidationError


class AgentImportGate:
    """Implements ``application.sync.ports.ImportGate`` structurally."""

    kind = "agent"

    def __init__(self, platform: PlatformPort) -> None:
        self._platform = platform

    async def validate(self, config: Mapping[str, object]) -> None:
        try:
            cfg = AgentConfig.model_validate(dict(config))
        except Exception as e:
            raise ConfigValidationError(str(e)) from e
        # Same machine-local precondition as AgentService.register: the config
        # dir must already exist here (the agent is installed) and the skill
        # subdir must be usable. A missing config dir means the agent is not
        # installed on this machine — AgentConfigDirMissing, which the round
        # records as not applicable here instead of retrying it every round.
        # An unusable skill dir stays SkillDirNotWritable → retried.
        config_dir = cfg.resolved_config_dir()
        if not await asyncio.to_thread(config_dir.is_dir):
            raise AgentConfigDirMissing(str(config_dir))
        await asyncio.to_thread(
            ensure_skill_dir,
            cfg.resolved_config_dir(),
            cfg.resolved_skill_dir(),
            self._platform.privileged_paths(),
        )
