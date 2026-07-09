"""Skill-delivery facet of the capability manifest (spec 005).

Split out of ``descriptor.py`` for the file-size limit, mirroring how
``mcp_injection.py`` carries its facet's value objects. The
:class:`AgentDescriptor` references :class:`SkillDeliveryMode` to declare *how*
Coffer hands a managed skill to each agent.

Every supported agent type uses the ``FOLDER`` mode: Coffer delivers a skill by
symlinking (copy-fallback) the master skill folder into the agent's skill
directory. The non-folder modes are recognized extension points reserved for a
future agent type that consumes skills through a different surface (rule files,
external directories); no current agent type uses them.
"""

from __future__ import annotations

from enum import StrEnum


class SkillDeliveryMode(StrEnum):
    """How Coffer delivers a managed skill to an agent.

    The skill service dispatches on this discriminator (read through a
    composition-root resolver as a plain ``str`` to honour Contract 5) instead
    of switching on :class:`AgentType`.
    """

    #: Symlink (copy-fallback) the master skill folder into the agent's skill
    #: directory at ``<skill_dir>/<skill_name>`` — used by every supported agent
    #: type.
    FOLDER = "folder"
    #: Skills projected as ``.mdc`` rule files. Recognized extension point for a
    #: future agent type; no current agent type uses it.
    RULES_MDC = "rules_mdc"
    #: Skills registered as external directories. Recognized extension point for
    #: a future agent type; no current agent type uses it.
    EXTERNAL_DIR = "external_dir"
