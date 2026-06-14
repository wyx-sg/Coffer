"""Skill-delivery facet of the capability manifest (spec 005).

Split out of ``descriptor.py`` for the file-size limit, mirroring how
``mcp_injection.py`` / ``plugin_state_extra.py`` carry their facet's value
objects. The :class:`AgentDescriptor` references :class:`SkillDeliveryMode`
to declare *how* Coffer hands a managed skill to each agent.

Coffer delivers a skill by symlinking (copy-fallback) the master skill folder
into the agent's skill directory — the ``FOLDER`` mode. Agents that consume
skills through a different surface (Cursor's ``.mdc`` rules, Hermes' external
directories) declare a non-folder mode; their delivery is a recognized
extension point that a follow-up wires end-to-end.
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
    #: directory at ``<skill_dir>/<skill_name>`` — Claude Code, Codex, OpenCode,
    #: OpenClaw.
    FOLDER = "folder"
    #: Cursor — skills are projected as ``.mdc`` rule files. Recognized
    #: extension point; not yet delivered.
    RULES_MDC = "rules_mdc"
    #: Hermes — skills are registered as external directories. Recognized
    #: extension point; not yet delivered.
    EXTERNAL_DIR = "external_dir"
