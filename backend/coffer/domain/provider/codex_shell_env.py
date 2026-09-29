"""Keep the projected provider key out of the shell commands Codex runs.

Codex reads the key from ``COFFER_PROVIDER_KEY`` (the projected ``env_key``)
and, by default, passes its whole environment to every shell command the agent
runs: ``shell_environment_policy`` defaults to ``inherit = "all"`` with the
built-in KEY/SECRET/TOKEN filter off (``ignore_default_excludes = true``). So
the Codex projection names the variable in ``exclude``, and de-projection takes
only that entry back out. Pure transforms on a parsed ``tomlkit`` document.
"""

from __future__ import annotations

from collections.abc import MutableMapping

import tomlkit

#: Codex's table deciding which environment variables reach its shell commands.
CODEX_SHELL_ENV_POLICY_KEY = "shell_environment_policy"


def exclude_from_shell_env(doc: MutableMapping[str, object], env_key: str) -> None:
    """Add ``env_key`` to ``shell_environment_policy.exclude``, keeping the
    user's own entries and any other policy keys. A hand-edit that left a
    non-table policy or a non-array ``exclude`` is replaced, as
    ``model_providers`` is — Codex would refuse to load either anyway."""
    policy = doc.get(CODEX_SHELL_ENV_POLICY_KEY)
    if not isinstance(policy, MutableMapping):
        policy = tomlkit.table()
        doc[CODEX_SHELL_ENV_POLICY_KEY] = policy
    exclude = policy.get("exclude")
    if not isinstance(exclude, list):
        exclude = tomlkit.array()
        policy["exclude"] = exclude
    if env_key not in exclude:
        exclude.append(env_key)


def drop_shell_env_exclude(doc: MutableMapping[str, object], env_key: str) -> None:
    """Inverse of :func:`exclude_from_shell_env`: remove ``env_key`` from the
    ``exclude`` list, then the list and the table if that left them empty."""
    policy = doc.get(CODEX_SHELL_ENV_POLICY_KEY)
    if not isinstance(policy, MutableMapping):
        return
    exclude = policy.get("exclude")
    if isinstance(exclude, list):
        while env_key in exclude:
            exclude.remove(env_key)
        if not exclude:
            policy.pop("exclude", None)
    if not policy:
        doc.pop(CODEX_SHELL_ENV_POLICY_KEY, None)
