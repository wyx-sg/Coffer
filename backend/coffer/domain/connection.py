"""Kind-agnostic contract between the provider projection and the chat adapters.

Two kinds have to agree on one string: the ``provider`` kind writes it into
Codex's ``config.toml`` as the ``env_key`` of the provider block it manages,
and the ``chat`` kind's Codex adapter materialises the resolved key into that
same environment variable when it spawns the agent. Neither kind may import
the other (import-linter cross-kind contracts), so the name lives here, in the
kind-agnostic domain, and both read it from this module.
"""

from __future__ import annotations

#: The env var Codex reads the API key from (``model_providers.coffer.env_key``).
#: The raw key is materialised into this var at runtime, never written to disk.
CODEX_ENV_KEY = "COFFER_PROVIDER_KEY"
