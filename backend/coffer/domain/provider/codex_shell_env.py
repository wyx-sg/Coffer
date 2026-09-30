"""Clean up the shell-environment exclusion earlier builds added to Codex.

Before the local model proxy, the Codex projection named an ``env_key``
(``COFFER_PROVIDER_KEY``) holding the provider key, and — because Codex passes
its whole environment to every shell command the agent runs — listed that
variable in ``shell_environment_policy.exclude``. Coffer now authenticates
Codex through the provider block's ``auth`` command and names no variable, but
files an earlier build wrote still carry the exclusion, so every projection
write and every de-projection takes that one entry back out (spec
provider-switching "Project into Codex config without clobbering it"). Pure
transform on a parsed ``tomlkit`` document.
"""

from __future__ import annotations

from collections.abc import MutableMapping

#: Codex's table deciding which environment variables reach its shell commands.
CODEX_SHELL_ENV_POLICY_KEY = "shell_environment_policy"
#: The variable earlier builds named as the provider block's ``env_key`` and
#: excluded from shell commands. Recognised for cleanup, never written.
LEGACY_CODEX_ENV_KEY = "COFFER_PROVIDER_KEY"


def drop_legacy_shell_env_exclude(doc: MutableMapping[str, object]) -> None:
    """Remove :data:`LEGACY_CODEX_ENV_KEY` from ``shell_environment_policy.exclude``,
    then the list and the table if that left them empty. The user's own
    entries and other policy keys stay."""
    policy = doc.get(CODEX_SHELL_ENV_POLICY_KEY)
    if not isinstance(policy, MutableMapping):
        return
    exclude = policy.get("exclude")
    if isinstance(exclude, list):
        while LEGACY_CODEX_ENV_KEY in exclude:
            exclude.remove(LEGACY_CODEX_ENV_KEY)
        if not exclude:
            policy.pop("exclude", None)
    if not policy:
        doc.pop(CODEX_SHELL_ENV_POLICY_KEY, None)
