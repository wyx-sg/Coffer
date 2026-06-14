"""External-directory skill-delivery value object (spec 005, EXTERNAL_DIR mode).

Some agents do not consume a skill by having its folder symlinked into a
fixed ``<config_dir>/skills`` location; instead they *scan* a list of external
directories declared in their own config file (Hermes' ``skills.external_dirs``
in ``~/.hermes/config.yaml``). For those agents Coffer folder-delivers the
enabled skills into a Coffer-owned directory and registers that directory in
the agent's config.

This dataclass is the agent-agnostic description of *where* that registration
lives. It is built at the composition root (the only layer allowed to read the
agent's capability descriptor — Contract 5) and handed to the infrastructure
registrar, so neither the skill application layer nor the registrar adapter
ever imports agent-kind code.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalDirRegistration:
    """Where (and how) to register a Coffer-owned external skill directory.

    - ``config_path`` — the agent's own config file to edit (e.g.
      ``~/.hermes/config.yaml``).
    - ``external_dir`` — the Coffer-owned directory that holds the delivered
      skill folders and is registered with the agent.
    - ``container_keys`` — the nested mapping path to the list of external
      directories inside the config file (e.g. ``("skills", "external_dirs")``).
    """

    config_path: pathlib.Path
    external_dir: pathlib.Path
    container_keys: tuple[str, ...]
